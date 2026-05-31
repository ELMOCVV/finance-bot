from datetime import datetime, date

DATE_FORMAT = "%d.%m.%Y"
DATE_HINT = "ДД.ММ.РРРР (наприклад: 30.10.2026)"


def fmt_date(d: date | None) -> str:
    return d.strftime(DATE_FORMAT) if d else "—"


def parse_date(text: str) -> date:
    """Raises ValueError if format is wrong."""
    return datetime.strptime(text.strip(), DATE_FORMAT).date()
