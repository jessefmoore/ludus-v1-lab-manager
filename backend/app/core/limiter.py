"""Shared rate limiter instance.

Separated into its own module to avoid circular imports between
``app.main`` and ``app.api.auth``.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    enabled=_settings.app_env not in ("testing", "test"),
)
