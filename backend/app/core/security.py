from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _fernet(key: str | None = None) -> Fernet:
    secret = key or get_settings().effective_secret
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value: str, key: str | None = None) -> str:
    return _fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str, key: str | None = None) -> str:
    try:
        return _fernet(key).decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("cannot decrypt value with current SECRET_KEY") from exc


def mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 6:
        return "•" * len(secret)
    return f"{secret[:3]}{'•' * 6}{secret[-4:]}"
