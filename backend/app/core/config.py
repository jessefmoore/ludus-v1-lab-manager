"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, env-driven configuration for the insec-platform backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Platform
    app_env: str = "development"
    app_secret_key: str
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Instructor admin bootstrap
    admin_email: EmailStr
    admin_password: str

    # Database
    database_url: str = "sqlite:///./data/insec.db"

    # Ludus
    ludus_default_url: str
    ludus_default_api_key: str
    ludus_default_verify_tls: bool = False

    # Invite
    invite_token_ttl_hours: int = 168
    public_base_url: str = "http://localhost:8000"

    # File storage
    config_storage_dir: str = "./data/configs"


@lru_cache
def get_settings() -> Settings:
    """Return a memoised Settings singleton populated from env/.env."""
    return Settings()
