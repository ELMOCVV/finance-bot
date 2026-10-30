import json
import logging
from typing import Optional
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

# Системний промпт для парсингу транзакцій
PARSE_TRANSACTION_PROMPT = """Ти — фінансовий асистент. Парсуй повідомлення та витягуй фінансові транзакції.

Відповідай ВИКЛЮЧНО валідним JSON без жодного тексту навколо.

Структура транзакції:
{
  "type": "expense" | "income" | "transfer",
  "amount": число,
  "currency": "UAH" | "USD" | "USDT" | "EUR" | ...,
  "description": "опис",
  "category_hint": "категорія (їжа, транспорт, розваги, ...)",
  "account_hint": "рахунок (картка, готівка, ...) або null",
  "date_hint": null або "сьогодні" | "вчора" | ISO-дата
}

Якщо в повідомленні ОДНА транзакція — поверни JSON-об'єкт:
{"type": "expense", "amount": 50, "currency": "UAH", "description": "кофе", ...}

Якщо в повідомленні КІЛЬКА транзакцій (кілька рядків, кожен з сумою) — поверни JSON-масив:
[{"type": "expense", "amount": 50, ...}, {"type": "expense", "amount": 145, ...}]

Якщо не вдалось розпарсити — поверни {"error": "причина"}.
"""

# Позиції чека з розкладом за категоріями (розбивка витрати з Wallet)
PARSE_RECEIPT_ITEMS_PROMPT = """Ти — фінансовий асистент. На фото — касовий чек.
Випиши кожну куплену позицію з її підсумковою ціною (з урахуванням кількості та знижки на позицію)
і віднеси до однієї з категорій користувача (їх список у повідомленні).
Якщо жодна категорія не підходить (наприклад, тютюн чи алкоголь, а такої категорії немає) —
запропонуй коротку нову назву категорії українською в "new_category", а "category_id" постав null.

Відповідай ВИКЛЮЧНО валідним JSON без жодного тексту навколо:
{"items": [{"name": "Хліб", "amount": 32.5, "category_id": 3, "new_category": null},
           {"name": "Marlboro", "amount": 120, "category_id": null, "new_category": "Тютюн"}],
 "total": 152.5}

"total" — підсумок до сплати з чека. Якщо на фото не чек або його не прочитати —
поверни {"error": "причина"}.
"""

FINANCE_ASSISTANT_PROMPT ="""Ти — розумний фінансовий асистент застосунку FinanceAI Bot.
Відповідай лаконічно, по суті, українською мовою.
Допомагай аналізувати витрати, планувати бюджет, давати поради щодо заощаджень.
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
            return {"error": "Не вдалось розпарсити транзакцію"}
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
                                "text": "Розпізнай усі витрати/доходи на цьому чеку або скріншоті.",
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
        cats_str = "\n".join(f'id={c["id"]}: {c["name"]}' for c in categories) or "(немає)"
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
                            {"type": "text", "text": f"Категорії користувача:\n{cats_str}"},
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
                return {"error": "Неочікувана відповідь"}
            return parsed
        except Exception as e:
            logger.error("Помилка розпізнавання позицій чека: %s", e)
            return {"error": str(e)}

    async def answer_finance_question(
        self,
        question: str,
        context: Optional[str] = None,
    ) -> str:
        """Відповідає на фінансове питання з урахуванням контексту користувача."""
        messages = []
        if context:
            messages.append({"role": "user", "content": f"Контекст мого фінансового стану:\n{context}"})
            messages.append({"role": "assistant", "content": "Зрозумів, врахую ці дані."})
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
            return "Вибачте, сталась помилка при зверненні до AI. Спробуйте пізніше."


claude_service = ClaudeService()
