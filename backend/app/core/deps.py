"""FastAPI dependencies for auth-gated routes.

Re-exports ``get_db`` so that routers can import both the session and
the current-user dependency from a single place.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import LudusServerConfig, Settings, get_settings
from app.core.db import get_db
from app.core.security import COOKIE_NAME, decode_access_token
from app.models.user import User
from app.services.ludus import LudusClient

__all__ = [
    "LudusClientRegistry",
    "get_current_user",
    "get_db",
    "get_ludus_client",
    "get_ludus_client_registry",
]


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
) -> User:
    """Resolve the authenticated user from the session cookie.

    Raises 401 if the cookie is missing, the JWT is invalid/expired, or the
    referenced user no longer exists. The error message is intentionally
    generic to avoid leaking whether the account exists.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = decode_access_token(token, settings)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        ) from exc

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        ) from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return user


# ---------------------------------------------------------------------------
# Ludus client registry
# ---------------------------------------------------------------------------


class LudusClientRegistry:
    """Registry of ``LudusClient`` instances keyed by server name.

    Lazily constructs clients on first access and caches them for the
    lifetime of the registry (process-scoped singleton via
    :func:`get_ludus_client_registry`).
    """

    def __init__(self, servers: dict[str, LudusServerConfig]) -> None:
        self._servers = servers
        self._clients: dict[str, LudusClient] = {}

    def get(self, name: str = "default") -> LudusClient:
        """Return the ``LudusClient`` for *name*, constructing on first use.

        Raises ``ValueError`` if *name* is not a configured server.
        """
        if name not in self._servers:
            raise ValueError(
                f"Unknown Ludus server '{name}'. "
                f"Configured: {', '.join(sorted(self._servers))}"
            )
        if name not in self._clients:
            cfg = self._servers[name]
            self._clients[name] = LudusClient(
                url=cfg.url,
                api_key=cfg.api_key,
                verify_tls=cfg.verify_tls,
            )
        return self._clients[name]

    @property
    def server_names(self) -> list[str]:
        """Sorted list of configured server names."""
        return sorted(self._servers)

    @property
    def servers(self) -> dict[str, LudusServerConfig]:
        """The underlying server config dict (read-only access)."""
        return self._servers

    def close_all(self) -> None:
        """Close all cached clients."""
        for client in self._clients.values():
            client.close()
        self._clients.clear()


@lru_cache
def _build_registry() -> LudusClientRegistry:
    """Construct a process-wide ``LudusClientRegistry`` from app settings."""
    s = get_settings()
    return LudusClientRegistry(s.ludus_servers)


def get_ludus_client_registry() -> LudusClientRegistry:
    """FastAPI dependency returning a memoised ``LudusClientRegistry``.

    Tests override this via ``app.dependency_overrides[get_ludus_client_registry]``.
    """
    return _build_registry()


@lru_cache
def _build_ludus_client() -> LudusClient:
    """Construct a process-wide ``LudusClient`` from app settings."""
    s = get_settings()
    return LudusClient(
        url=s.ludus_default_url,
        api_key=s.ludus_default_api_key,
        verify_tls=s.ludus_default_verify_tls,
    )


def get_ludus_client() -> LudusClient:
    """FastAPI dependency returning a memoised ``LudusClient``.

    Tests override this via ``app.dependency_overrides[get_ludus_client]``
    so that no real Ludus server is required.
    """
    return _build_ludus_client()
