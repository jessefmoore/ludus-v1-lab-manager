"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property, lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class LudusServerConfig:
    """Configuration for a single Ludus server discovered from env vars."""

    name: str
    url: str
    api_key: str
    verify_tls: bool = False
    # Optional separate admin-API URL. On Ludus v1, user create/delete are
    # served only by the admin API (127.0.0.1:8081); everything else uses
    # ``url``. Leave None on newer Ludus where one URL serves everything.
    admin_url: str | None = None


class Settings(BaseSettings):
    """Typed, env-driven configuration for the ludus-helm backend."""

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
    admin_email: str
    admin_password: str

    # Database
    database_url: str = "sqlite:///./data/insec.db"

    # Ludus
    ludus_default_url: str
    ludus_default_api_key: str
    ludus_default_verify_tls: bool = False
    # Optional admin-API URL for Ludus v1 user management (see LudusServerConfig).
    ludus_default_admin_url: str | None = None

    # Invite
    invite_token_ttl_hours: int = 168
    public_base_url: str = "http://localhost:8000"

    # File storage
    config_storage_dir: str = "./data/configs"

    # Seed a starter pack of Ludus v1 range configs into lab_templates on first
    # boot (once per seed version). Set false to start with no templates.
    seed_lab_templates: bool = True

    @cached_property
    def ludus_servers(self) -> dict[str, LudusServerConfig]:
        """Discover all configured Ludus servers from env vars.

        Always includes ``"default"`` from the ``ludus_default_*`` fields.
        Scans ``os.environ`` for ``LUDUS_<NAME>_URL`` patterns and extracts
        matching ``_API_KEY`` / ``_VERIFY_TLS``. Incomplete configs (missing
        API key) are silently skipped.
        """
        servers: dict[str, LudusServerConfig] = {
            "default": LudusServerConfig(
                name="default",
                url=self.ludus_default_url,
                api_key=self.ludus_default_api_key,
                verify_tls=self.ludus_default_verify_tls,
                admin_url=self.ludus_default_admin_url,
            ),
        }

        # Scan env for LUDUS_<NAME>_URL patterns (excluding DEFAULT which is
        # already handled above).
        seen: set[str] = set()
        for key in os.environ:
            upper = key.upper()
            if not upper.startswith("LUDUS_") or not upper.endswith("_URL"):
                continue
            # Extract the server name: LUDUS_<NAME>_URL -> <NAME>
            name = upper[len("LUDUS_") : -len("_URL")]
            # Skip DEFAULT (handled above) and the *_ADMIN_URL companion vars,
            # which configure a server's admin API rather than a new server.
            if not name or name == "DEFAULT" or name.endswith("_ADMIN") or name in seen:
                continue
            seen.add(name)

            url = os.environ[key]
            api_key = os.environ.get(f"LUDUS_{name}_API_KEY", "")
            if not api_key:
                continue  # skip incomplete configs

            verify_raw = os.environ.get(f"LUDUS_{name}_VERIFY_TLS", "false")
            verify_tls = verify_raw.lower() in ("true", "1", "yes")

            servers[name.lower()] = LudusServerConfig(
                name=name.lower(),
                url=url,
                api_key=api_key,
                verify_tls=verify_tls,
                admin_url=os.environ.get(f"LUDUS_{name}_ADMIN_URL"),
            )

        return servers


@lru_cache
def get_settings() -> Settings:
    """Return a memoised Settings singleton populated from env/.env."""
    return Settings()
