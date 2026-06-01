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

FINANCE_ASSISTANT_PROMPT = """Ти — розумний фінансовий асистент застосунку FinanceAI Bot.
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
