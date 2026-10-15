"""Fernet encryption for connector refresh tokens."""

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    return Fernet(
        settings.CONNECTOR_TOKEN_KEY.encode()
        if isinstance(settings.CONNECTOR_TOKEN_KEY, str)
        else settings.CONNECTOR_TOKEN_KEY
    )


def encrypt_token(raw: str) -> bytes:
    return _fernet().encrypt(raw.encode("utf-8"))


def decrypt_token(blob: bytes) -> str:
    return _fernet().decrypt(bytes(blob)).decode("utf-8")
