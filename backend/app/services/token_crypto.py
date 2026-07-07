"""Симетричне шифрування банківських токенів (Fernet).

Ключ береться з env TOKEN_ENCRYPTION_KEY. Якщо значення — валідний
Fernet-ключ (32 url-safe base64 байти), він використовується напряму;
інакше з довільного рядка деривується стабільний 32-байтний ключ через
SHA-256. Токени ніколи не зберігаються і не логуються у відкритому вигляді.
"""
import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.TOKEN_ENCRYPTION_KEY)


@lru_cache()
def _fernet() -> Fernet | None:
    raw = settings.TOKEN_ENCRYPTION_KEY
    if not raw:
        logger.warning("TOKEN_ENCRYPTION_KEY не задано — шифрування токенів недоступне.")
        return None
    try:
        return Fernet(raw)
    except Exception:
        # Довільний рядок → стабільний Fernet-ключ через SHA-256
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        return Fernet(derived)


def encrypt_token(token: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY не налаштовано")
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY не налаштовано")
    return f.decrypt(encrypted.encode()).decode()
