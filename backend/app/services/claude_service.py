import json
import logging
from typing import Optional
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

# Системный промпт для разбора транзакций
PARSE_TRANSACTION_PROMPT = """Ты — финансовый ассистент. Разбирай сообщение и извлекай финансовые транзакции.

Отвечай ИСКЛЮЧИТЕЛЬНО валидным JSON без какого-либо текста вокруг.

Структура транзакции:
{
  "type": "expense" | "income" | "transfer",
  "amount": число,
  "currency": "UAH" | "USD" | "USDT" | "EUR" | ...,
  "description": "описание на русском",
  "category_hint": "категория (еда, транспорт, развлечения, ...)",
  "account_hint": "счёт (карта, наличные, ...) или null",
  "date_hint": null или "сегодня" | "вчера" | ISO-дата
}

Если в сообщении ОДНА транзакция — верни JSON-объект:
{"type": "expense", "amount": 50, "currency": "UAH", "description": "кофе", ...}

Если в сообщении НЕСКОЛЬКО транзакций (несколько строк, у каждой своя сумма) — верни JSON-массив:
[{"type": "expense", "amount": 50, ...}, {"type": "expense", "amount": 145, ...}]

Если разобрать не получилось — верни {"error": "причина"}.
"""

# Позиции чека с раскладкой по категориям (разбивка расхода из Wallet)
PARSE_RECEIPT_ITEMS_PROMPT = """Ты — финансовый ассистент. На фото — кассовый чек.
Выпиши каждую купленную позицию с её итоговой ценой (с учётом количества и скидки на позицию)
и отнеси к одной из категорий пользователя (их список — в сообщении).
Если ни одна категория не подходит (например, табак или алкоголь, а такой категории нет) —
предложи короткое новое название категории на русском в "new_category" и один эмодзи в "new_icon",
а "category_id" поставь null. Названия позиций пиши как в чеке.

Отвечай ИСКЛЮЧИТЕЛЬНО валидным JSON без какого-либо текста вокруг:
{"items": [{"name": "Хлеб", "amount": 32.5, "category_id": 3, "new_category": null},
           {"name": "Marlboro", "amount": 120, "category_id": null, "new_category": "Табак", "new_icon": "🚬"}],
 "total": 152.5}

"total" — итог к оплате по чеку. Если на фото не чек или его не прочитать —
верни {"error": "причина"}.
"""

# Описание покупки текстом → позиции с категориями (шаг «Что купил?» для расходов из Wallet)
PARSE_PURCHASE_TEXT_PROMPT = """Ты — финансовый ассистент. Пользователь описал, что купил одной оплатой.
Сумма оплаты и список его категорий — в сообщении. Разбей описание на позиции и отнеси каждую
к категории по тому, ЧТО куплено (а не по магазину). Однотипные вещи можно объединить в одну позицию.
Если цена указана — "amount": число, "estimated": false. Если нет — оцени типичную цену в Украине,
"estimated": true (точные суммы потом вычитаются из суммы оплаты, остаток делится между оценками).
Если ни одна категория не подходит (например, табак или алкоголь, а такой нет) —
"category_id": null, короткое новое название на русском в "new_category" и один эмодзи в "new_icon".
Если в описании одна вещь или всё одного типа — одна позиция. Названия позиций — на языке пользователя.

Отвечай ИСКЛЮЧИТЕЛЬНО валидным JSON без какого-либо текста вокруг:
{"items": [{"name": "хлеб, молоко", "amount": 300, "estimated": false, "category_id": 3, "new_category": null},
           {"name": "сигареты", "amount": 150, "estimated": false, "category_id": null, "new_category": "Табак", "new_icon": "🚬"}]}

Если это не описание покупки — верни {"error": "причина"}.
"""

FINANCE_ASSISTANT_PROMPT = """Ты — умный финансовый ассистент приложения FinanceAI Bot.
Отвечай кратко, по делу, на русском языке.
Помогай анализировать расходы, планировать бюджет, давай советы по сбережениям.
"""


class ClaudeService:
    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-6"

    async def parse_transaction(self, text: str) -> "dict | list":
        """Парсить текст повідомлення. Повертає dict (одна транзакція або error) або list (кілька)."""
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=PARSE_TRANSACTION_PROMPT,
                messages=[{"role": "user", "content": text}],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error("Помилка парсингу JSON від Claude: %s", e)
            return {"error": "Не удалось разобрать транзакцию"}
        except Exception as e:
            logger.error("Помилка Claude API: %s", e)
            return {"error": str(e)}

    async def parse_receipt_photo(self, image_base64: str, media_type: str = "image/jpeg") -> dict:
        """Розпізнає чек із фото та повертає список транзакцій."""
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=PARSE_TRANSACTION_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": "Распознай все расходы/доходы на этом чеке или скриншоте.",
                            },
                        ],
                    }
                ],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            logger.error("Помилка розпізнавання фото: %s", e)
            return {"error": str(e)}

    async def parse_receipt_items(
        self, image_base64: str, categories: list[dict], media_type: str = "image/jpeg",
    ) -> dict:
        """Розпізнає позиції чека й відносить кожну до категорії користувача.

        categories — [{"id": int, "name": str}] витратних категорій.
        Повертає {"items": [{"name", "amount", "category_id", "new_category"}], "total"}
        або {"error": "..."}.
        """
        cats_str = "\n".join(f'id={c["id"]}: {c["name"]}' for c in categories) or "(нет)"
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=PARSE_RECEIPT_ITEMS_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": image_base64},
                            },
                            {"type": "text", "text": f"Категории пользователя:\n{cats_str}"},
                        ],
                    }
                ],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or ("items" not in parsed and "error" not in parsed):
                return {"error": "Неожиданный ответ"}
            return parsed
        except Exception as e:
            logger.error("Помилка розпізнавання позицій чека: %s", e)
            return {"error": str(e)}

    async def parse_purchase_text(
        self, text: str, total: float, currency: str, categories: list[dict],
    ) -> dict:
        """Опис покупки → {"items": [...]} як у parse_receipt_items, або {"error": ...}."""
        cats_str = "\n".join(f'id={c["id"]}: {c["name"]}' for c in categories) or "(нет)"
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=PARSE_PURCHASE_TEXT_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Сумма оплаты: {total} {currency}\nКатегории пользователя:\n{cats_str}\n\nОписание: {text}",
                }],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or ("items" not in parsed and "error" not in parsed):
                return {"error": "Неожиданный ответ"}
            return parsed
        except Exception as e:
            logger.error("Помилка розбору опису покупки: %s", e)
            return {"error": str(e)}

    async def answer_finance_question(
        self,
        question: str,
        context: Optional[str] = None,
    ) -> str:
        """Відповідає на фінансове питання з урахуванням контексту користувача."""
        messages = []
        if context:
            messages.append({"role": "user", "content": f"Контекст моего финансового положения:\n{context}"})
            messages.append({"role": "assistant", "content": "Понял, учту эти данные."})
        messages.append({"role": "user", "content": question})

        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=FINANCE_ASSISTANT_PROMPT,
                messages=messages,
            )
            return message.content[0].text
        except Exception as e:
            logger.error("Помилка Claude API: %s", e)
            return "Извини, произошла ошибка при обращении к AI. Попробуй позже."


claude_service = ClaudeService()
