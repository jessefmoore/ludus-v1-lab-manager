"""Tests for the Fernet encryption utility."""

from __future__ import annotations

import pytest
from cryptography.fernet import InvalidToken

from app.core.encryption import decrypt_value, encrypt_value


def test_roundtrip() -> None:
    """Encrypt then decrypt returns the original plaintext."""
    secret = "my-app-secret-key"
    plaintext = "super-secret-api-key-12345"
    ciphertext = encrypt_value(plaintext, secret)
    assert ciphertext != plaintext
    assert decrypt_value(ciphertext, secret) == plaintext


def test_wrong_secret_raises() -> None:
    """Decrypting with a different secret raises InvalidToken."""
    ciphertext = encrypt_value("some-value", "correct-secret")
    with pytest.raises(InvalidToken):
        decrypt_value(ciphertext, "wrong-secret")


def test_different_secrets_produce_different_ciphertext() -> None:
    """Same plaintext encrypted with different secrets produces different output."""
    plaintext = "api-key-abc"
    ct1 = encrypt_value(plaintext, "secret-a")
    ct2 = encrypt_value(plaintext, "secret-b")
    assert ct1 != ct2
