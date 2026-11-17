import json
import logging
from anthropic import AsyncAnthropic
from app.config import settings

logger = logging.getLogger(__name__)
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


async def match_category(
    description: str,
    hint: str,
    tx_type: str,
    user_categories: list[dict],  # [{"id": int, "name": str}, ...]
) -> dict:
    """
    Підбирає існуючу категорію або пропонує нову.
    Повертає {"matched_id": int, "name": str} або {"new_name": str}.
    """
    if not user_categories:
        return {"new_name": hint or "Другое"}

    # Швидкий пошук по ключовому слову (без API)
    hint_lower = (hint or "").lower()
    desc_lower = description.lower()
    for cat in user_categories:
        cat_lower = cat["name"].lower()
        if hint_lower and (hint_lower in cat_lower or cat_lower in hint_lower):
            return {"matched_id": cat["id"], "name": cat["name"]}
        if cat_lower in desc_lower:
            return {"matched_id": cat["id"], "name": cat["name"]}

    # Claude Haiku для розумного підбору (швидко і дешево)
    if not settings.ANTHROPIC_API_KEY:
        return {"new_name": hint or "Другое"}

    cats_str = "\n".join(f'id={c["id"]}: {c["name"]}' for c in user_categories)
    prompt = (
        f'Транзакция ({tx_type}): "{description}". Подсказка: "{hint}".\n'
        f'Категории пользователя:\n{cats_str}\n\n'
        f'Выбери самую подходящую категорию или предложи новую (название на русском).\n'
        f'Ответ ТОЛЬКО JSON (без текста):\n'
        f'{{"matched_id": <число>}} или {{"new_name": "<название>"}}'
    )

    try:
        resp = await _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        # Прибираємо можливі ```json``` обгортки
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        result = json.loads(raw)
        if "matched_id" in result:
            cat = next((c for c in user_categories if c["id"] == int(result["matched_id"])), None)
            if cat:
                return {"matched_id": cat["id"], "name": cat["name"]}
        return {"new_name": result.get("new_name") or hint or "Другое"}
    except Exception as e:
        logger.warning("Category matching error: %s", e)
        return {"new_name": hint or "Другое"}
