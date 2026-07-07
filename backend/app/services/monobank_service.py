"""Клієнт Monobank Open API (https://api.monobank.ua/docs).

Особливості:
* Особистий токен передається у заголовку X-Token. Токен НІКОЛИ не логується.
* Ліміт швидкості особистого API — 1 запит на 60 секунд. Найважчий і
  найчутливіший до ліміту ендпоінт — виписка (statement); саме він проходить
  через глобальний throttle. Виклики виконуються послідовно (черга по картках),
  а не паралельно.
* Сума операцій приходить у копійках → ділимо на 100. Операції з hold=true
  (незавершені) ігноруються.
"""
import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Максимальне вікно виписки за один запит: 31 доба + 1 рік (за докою Monobank).
STATEMENT_MAX_RANGE = 60 * 60 * 24 * 31 + 60 * 60 * 24 * 366
# Мінімальний інтервал між запитами виписки (ліміт 1 req / 60 s).
_RATE_LIMIT_SECONDS = 60.0

# ISO 4217 числовий → буквений код (найпоширеніші валюти).
_CURRENCY_NUM_TO_ALPHA: dict[int, str] = {
    980: "UAH", 840: "USD", 978: "EUR", 826: "GBP", 985: "PLN",
    756: "CHF", 985: "PLN", 203: "CZK", 348: "HUF", 949: "TRY",
}

# MCC → підказка категорії (узгоджено з базовими категоріями застосунку).
_MCC_HINTS: dict[int, str] = {}
for _mcc in (5411, 5412, 5422, 5441, 5451, 5462, 5499,
             5811, 5812, 5813, 5814, 5921):
    _MCC_HINTS[_mcc] = "Їжа"
for _mcc in (4111, 4121, 4131, 4784, 4789, 5172, 5541, 5542, 7511, 7523):
    _MCC_HINTS[_mcc] = "Транспорт"
for _mcc in (5122, 5292, 5295, 5912, 8011, 8021, 8031, 8042, 8043, 8049, 8062, 8071, 8099):
    _MCC_HINTS[_mcc] = "Здоров'я"
for _mcc in (5611, 5621, 5631, 5641, 5651, 5661, 5691, 5699, 5948):
    _MCC_HINTS[_mcc] = "Одяг"
for _mcc in (5815, 5816, 5817, 5818, 7832, 7841, 7911, 7922, 7929,
             7991, 7996, 7997, 7998, 7999):
    _MCC_HINTS[_mcc] = "Розваги"
for _mcc in (4814, 4816, 4899, 4900):
    _MCC_HINTS[_mcc] = "Комунальні"


def currency_alpha(code: int | None) -> str:
    """ISO 4217 числовий код → буквений (fallback: UAH)."""
    if code is None:
        return "UAH"
    return _CURRENCY_NUM_TO_ALPHA.get(int(code), "UAH")


def mcc_to_hint(mcc: int | None) -> str:
    """Підказка категорії за MCC (порожній рядок, якщо невідомо)."""
    if mcc is None:
        return ""
    return _MCC_HINTS.get(int(mcc), "")


def parse_statement_item(item: dict[str, Any], currency_code: int) -> dict | None:
    """StatementItem → нормалізована операція або None (якщо hold=true).

    Повертає dict: amount (додатнє число), tx_type (expense|income),
    description, mcc, currency, mono_id, timestamp.
    """
    if item.get("hold") is True:
        return None
    raw = item.get("amount", 0)
    amount = abs(raw) / 100
    tx_type = "income" if raw > 0 else "expense"
    return {
        "mono_id": item.get("id"),
        "amount": amount,
        "tx_type": tx_type,
        "description": (item.get("description") or "").strip(),
        "mcc": item.get("mcc"),
        "currency": currency_alpha(currency_code),
        "timestamp": item.get("time"),
    }


class MonobankService:
    def __init__(self) -> None:
        self._throttle_lock = asyncio.Lock()
        # monotonic-час останнього запиту виписки; 0 → перший виклик без очікування
        self._last_statement_ts = 0.0

    @property
    def _base(self) -> str:
        return settings.MONOBANK_API_URL.rstrip("/")

    async def get_client_info(self, token: str) -> dict:
        """GET /personal/client-info — інформація про клієнта та рахунки."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                f"{self._base}/personal/client-info",
                headers={"X-Token": token},
            )
            resp.raise_for_status()
            return resp.json()

    async def set_webhook(self, token: str, url: str) -> bool:
        """POST /personal/webhook — реєстрація URL для вхідних подій."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{self._base}/personal/webhook",
                headers={"X-Token": token},
                json={"webHookUrl": url},
            )
            resp.raise_for_status()
            return True

    async def _throttle_statement(self) -> None:
        """Гарантує щонайменше 60 с між запитами виписки (послідовно)."""
        async with self._throttle_lock:
            elapsed = time.monotonic() - self._last_statement_ts
            wait = _RATE_LIMIT_SECONDS - elapsed
            if self._last_statement_ts and wait > 0:
                logger.info("Monobank statement throttle: очікування %.1f с", wait)
                await asyncio.sleep(wait)
            self._last_statement_ts = time.monotonic()

    async def get_statement(
        self, token: str, account_id: str, from_ts: int, to_ts: int
    ) -> list[dict]:
        """GET /personal/statement/{account}/{from}/{to} — виписка за період.

        Максимум 31 доба + 1 рік за один запит. Дотримується ліміту
        1 запит / 60 с через глобальний throttle.
        """
        if to_ts - from_ts > STATEMENT_MAX_RANGE:
            raise ValueError("Період виписки перевищує максимум (31 доба + 1 рік)")

        await self._throttle_statement()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{self._base}/personal/statement/{account_id}/{from_ts}/{to_ts}",
                headers={"X-Token": token},
            )
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, list) else []


monobank_service = MonobankService()
