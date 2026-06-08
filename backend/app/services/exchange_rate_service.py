import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from app.config import settings

logger = logging.getLogger(__name__)

# Внутрішній кеш: {(from, to): (rate, expires_at)}
_cache: dict[tuple[str, str], tuple[float, datetime]] = {}


class ExchangeRateService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def get_rate(self, currency_from: str, currency_to: str) -> Optional[float]:
        """Повертає курс currency_from -> currency_to. Кешує на 1 годину."""
        key = (currency_from.upper(), currency_to.upper())

        # Перевіряємо кеш
        if key in _cache:
            rate, expires_at = _cache[key]
            if datetime.utcnow() < expires_at:
                return rate

        async with self._lock:
            # Подвійна перевірка після отримання блокування
            if key in _cache:
                rate, expires_at = _cache[key]
                if datetime.utcnow() < expires_at:
                    return rate

            rate = await self._fetch_rate(*key)
            if rate is not None:
                _cache[key] = (rate, datetime.utcnow() + timedelta(seconds=settings.EXCHANGE_RATE_CACHE_TTL))
            return rate

    async def convert(self, amount: float, currency_from: str, currency_to: str) -> Optional[float]:
        """Конвертує суму з однієї валюти в іншу."""
        if currency_from.upper() == currency_to.upper():
            return amount
        rate = await self.get_rate(currency_from, currency_to)
        if rate is None:
            return None
        return round(amount * rate, 2)

    async def to_uah(self, amount: float, currency: str) -> float:
        """Конвертує суму в гривні. Повертає саму суму, якщо курс недоступний."""
        if currency.upper() == "UAH":
            return amount
        result = await self.convert(amount, currency, "UAH")
        return result if result is not None else amount

    async def _fetch_rate(self, currency_from: str, currency_to: str) -> Optional[float]:
        """Запитує курс: НБУ для фіатних (з фолбеком на CoinGecko), CoinGecko для крипти."""
        crypto_ids = {"USDT": "tether", "BTC": "bitcoin", "ETH": "ethereum"}

        try:
            if currency_from in crypto_ids:
                return await self._fetch_crypto_rate(crypto_ids[currency_from], currency_to)
            if currency_to in crypto_ids:
                # Зворотній курс через крипто
                rate = await self._fetch_crypto_rate(crypto_ids[currency_to], currency_from)
                return 1 / rate if rate else None

            try:
                rate = await self._fetch_nbu_rate(currency_from, currency_to)
            except Exception as e:
                rate = None
                logger.warning("НБУ API недоступне для %s->%s (%s)", currency_from, currency_to, e)

            if rate is not None:
                return rate

            logger.warning("НБУ не дав курс %s->%s, фолбек на CoinGecko", currency_from, currency_to)
            return await self._fetch_fiat_rate_via_coingecko(currency_from, currency_to)
        except Exception as e:
            logger.error("Помилка отримання курсу %s->%s: %s", currency_from, currency_to, e)
            return None

    async def _fetch_nbu_rate(self, currency_from: str, currency_to: str) -> Optional[float]:
        """Курс фіатних валют через НБУ API.

        НБУ зберігає курси відносно UAH і НЕ містить запису для самої UAH
        (вона базова) — тому для UAH курс до неї дорівнює 1, а не запитується.
        """
        if currency_from == currency_to:
            return 1.0

        async with httpx.AsyncClient(timeout=10.0) as client:
            rate_from_uah = 1.0 if currency_from == "UAH" else await self._fetch_nbu_single(client, currency_from)
            if rate_from_uah is None:
                return None
            rate_to_uah = 1.0 if currency_to == "UAH" else await self._fetch_nbu_single(client, currency_to)
            if rate_to_uah is None:
                return None
            return rate_from_uah / rate_to_uah

    async def _fetch_nbu_single(self, client: httpx.AsyncClient, valcode: str) -> Optional[float]:
        """Курс однієї валюти до UAH (скільки UAH за 1 одиницю валюти) через НБУ API."""
        response = await client.get(settings.NBU_API_URL, params={"json": "", "valcode": valcode})
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        return data[0]["rate"]

    async def _fetch_fiat_rate_via_coingecko(self, currency_from: str, currency_to: str) -> Optional[float]:
        """Резервний курс фіат->фіат через CoinGecko: ціни USDT (≈ 1 USD) у двох валютах як міст."""
        if currency_from == currency_to:
            return 1.0
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.COINGECKO_API_URL}/simple/price",
                params={"ids": "tether", "vs_currencies": f"{currency_from.lower()},{currency_to.lower()}"},
            )
            response.raise_for_status()
            prices = response.json().get("tether", {})
            price_from = prices.get(currency_from.lower())
            price_to = prices.get(currency_to.lower())
            if not price_from or not price_to:
                return None
            # 1 USDT ≈ price_from currency_from ≈ price_to currency_to
            return price_to / price_from

    async def _fetch_crypto_rate(self, coin_id: str, vs_currency: str) -> Optional[float]:
        """Курс криптовалюти через CoinGecko."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.COINGECKO_API_URL}/simple/price",
                params={"ids": coin_id, "vs_currencies": vs_currency.lower()},
            )
            response.raise_for_status()
            data = response.json()
            return data.get(coin_id, {}).get(vs_currency.lower())


exchange_rate_service = ExchangeRateService()
