"""Symmetric encryption helpers for storing secrets (e.g. API keys) in the DB.

Uses Fernet with a key derived from ``APP_SECRET_KEY`` via PBKDF2.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT = b"ludus-helm-api-key-encryption"


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte Fernet key from *secret* using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def encrypt_value(plaintext: str, secret: str) -> str:
    """Encrypt *plaintext* with a key derived from *secret*, return URL-safe base64."""
    f = Fernet(_derive_key(secret))
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, secret: str) -> str:
    """Decrypt *ciphertext* using *secret*.

    Raises ``cryptography.fernet.InvalidToken`` on wrong key / corrupt data.
    """
    f = Fernet(_derive_key(secret))
    return f.decrypt(ciphertext.encode()).decode()


__all__ = ["InvalidToken", "decrypt_value", "encrypt_value"]
