"""Tests for app.core.config.Settings and get_settings()."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

REQUIRED_ENV = {
    "APP_SECRET_KEY": "unit-test-secret",
    "ADMIN_EMAIL": "admin@example.com",
    "ADMIN_PASSWORD": "unit-test-password",
    "LUDUS_DEFAULT_URL": "https://ludus.test:8080",
    "LUDUS_DEFAULT_API_KEY": "unit-test-api-key",
}


def _apply_env(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_settings_populated_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env vars flow through to Settings with correct types and defaults."""
    get_settings.cache_clear()
    _apply_env(monkeypatch, REQUIRED_ENV)
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("APP_PORT", "9001")
    monkeypatch.setenv("LUDUS_DEFAULT_VERIFY_TLS", "true")
    monkeypatch.setenv("INVITE_TOKEN_TTL_HOURS", "24")

    try:
        settings = get_settings()

        assert settings.app_env == "testing"
        assert settings.app_secret_key == "unit-test-secret"
        assert settings.app_host == "0.0.0.0"
        assert settings.app_port == 9001
        assert settings.admin_email == "admin@example.com"
        assert settings.admin_password == "unit-test-password"
        assert settings.database_url == "sqlite:///./data/insec.db"
        assert settings.ludus_default_url == "https://ludus.test:8080"
        assert settings.ludus_default_api_key == "unit-test-api-key"
        assert settings.ludus_default_verify_tls is True
        assert settings.invite_token_ttl_hours == 24
        assert settings.public_base_url == "http://localhost:8000"
        assert settings.config_storage_dir == "./data/configs"
    finally:
        get_settings.cache_clear()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_settings() returns the same object on repeated calls."""
    get_settings.cache_clear()
    _apply_env(monkeypatch, REQUIRED_ENV)

    try:
        first = get_settings()
        second = get_settings()
        assert first is second
    finally:
        get_settings.cache_clear()


def test_missing_required_fields_raises(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Omitting any required env var causes ValidationError."""
    get_settings.cache_clear()
    for key in (
        "APP_SECRET_KEY",
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "LUDUS_DEFAULT_URL",
        "LUDUS_DEFAULT_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    # Point env_file at an empty file so a stray local .env can't satisfy the fields.
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")

    try:
        with pytest.raises(ValidationError):
            Settings(_env_file=str(empty_env))
    finally:
        get_settings.cache_clear()
