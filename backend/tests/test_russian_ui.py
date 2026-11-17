"""Тексты бота — на русском: в строках, которые видит пользователь, нет украинских букв.

Пропускаются docstring'и, комментарии и сообщения логов (logger.*(...)).
"""
import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted([*ROOT.glob("bot/handlers/*.py"), *ROOT.glob("bot/keyboards/*.py"), *ROOT.glob("bot/utils/*.py"),
                ROOT / "bot/scheduler.py", ROOT / "bot/services/category_matcher.py",
                ROOT / "backend/app/services/claude_service.py", *ROOT.glob("backend/app/routers/*.py")])
UA = re.compile(r"[іїєґІЇЄҐʼ]")
# Сознательные исключения: старое название «Інше» распознаётся как «Другое»
ALLOWED = {("bot/handlers/transaction.py", '"Інше"')}


def user_strings(path: Path):
    toks = list(tokenize.generate_tokens(io.StringIO(path.read_text(encoding="utf-8")).readline))
    skip = {tokenize.NL, tokenize.COMMENT}
    for i, t in enumerate(toks):
        if t.type != tokenize.STRING:
            continue
        j = i - 1
        while j >= 0 and toks[j].type in skip:
            j -= 1
        k = i + 1
        while k < len(toks) and toks[k].type in skip:
            k += 1
        is_doc = (j < 0 or toks[j].type in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT)) \
            and toks[k].type in (tokenize.NEWLINE, tokenize.ENDMARKER)
        # logger.info( "..." — сообщения логов пользователь не видит
        is_log = j >= 3 and toks[j].string == "(" and toks[j - 2].string == "." and toks[j - 3].string == "logger"
        if not is_doc and not is_log:
            yield t.string


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_ukrainian_in_user_facing_strings(path):
    rel = str(path.relative_to(ROOT))
    bad = [s for s in user_strings(path) if UA.search(s) and (rel, s) not in ALLOWED]
    assert bad == []
