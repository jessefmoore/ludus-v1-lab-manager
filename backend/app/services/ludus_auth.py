"""Authenticate app logins against Ludus users' Proxmox credentials.

Ludus users are Proxmox (PAM) users. To let instructors log in with their
Ludus/Proxmox credentials instead of a separate app password, this validates a
submitted ``username`` + ``password`` by:

  1. Resolving ``username`` to a Ludus user (matching either the Ludus
     ``userID`` or the ``proxmoxUsername``) via the admin API, which yields the
     ``proxmoxUsername`` and ``isAdmin`` flag.
  2. Requesting a Proxmox auth ticket for ``<proxmoxUsername>@<realm>`` with the
     supplied password. A valid ticket means the password is correct.

Policy: when ``ludus_auth_admins_only`` is set (default), only Ludus admins are
allowed to authenticate (this is an instructor management console).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)


@dataclass
class LudusIdentity:
    """A Ludus user that successfully authenticated via Proxmox."""

    user_id: str
    proxmox_username: str
    is_admin: bool


def _find_ludus_user(users: list[dict], identifier: str) -> dict | None:
    """Match *identifier* against a user's Ludus userID or proxmoxUsername."""
    for u in users:
        if not isinstance(u, dict):
            continue
        if u.get("userID") == identifier or u.get("proxmoxUsername") == identifier:
            return u
    return None


def _proxmox_password_valid(
    proxmox_username: str, password: str, settings: Settings
) -> bool:
    """Return True if Proxmox issues an auth ticket for these credentials."""
    base = settings.resolved_proxmox_url
    if not base:
        logger.warning("ludus_auth: no Proxmox URL configured/derivable")
        return False
    try:
        resp = httpx.post(
            f"{base}/api2/json/access/ticket",
            data={
                "username": f"{proxmox_username}@{settings.proxmox_realm}",
                "password": password,
            },
            verify=settings.proxmox_verify_tls,
            timeout=10.0,
        )
    except httpx.RequestError as exc:
        logger.warning("ludus_auth: Proxmox unreachable at %s: %s", base, exc)
        return False
    if resp.status_code != 200:
        return False
    try:
        data = resp.json().get("data")
    except ValueError:
        return False
    return isinstance(data, dict) and bool(data.get("ticket"))


def authenticate_ludus(
    username: str,
    password: str,
    settings: Settings,
    *,
    ludus_client: LudusClient | None = None,
) -> LudusIdentity | None:
    """Validate *username*/*password* against Ludus/Proxmox.

    Returns a :class:`LudusIdentity` on success, or ``None`` if auth is
    disabled, the user is unknown, not permitted, or the password is wrong.
    Never raises on Ludus/Proxmox transport errors (treated as auth failure).
    """
    if not settings.ludus_auth_enabled:
        return None
    if not username or not password:
        return None

    owns_client = False
    if ludus_client is None:
        ludus_client = LudusClient(
            url=settings.ludus_default_url,
            api_key=settings.ludus_default_api_key,
            verify_tls=settings.ludus_default_verify_tls,
            admin_url=settings.ludus_default_admin_url,
        )
        owns_client = True
    try:
        users = ludus_client.user_list()
    except Exception as exc:  # noqa: BLE001 - any Ludus failure => cannot auth
        logger.warning("ludus_auth: user_list failed: %s", exc)
        return None
    finally:
        if owns_client:
            ludus_client.close()

    user = _find_ludus_user(users, username)
    if user is None:
        return None

    proxmox_username = user.get("proxmoxUsername")
    user_id = user.get("userID")
    is_admin = bool(user.get("isAdmin"))
    if not proxmox_username or not user_id:
        return None

    if settings.ludus_auth_admins_only and not is_admin:
        logger.warning("ludus_auth: user %s is not a Ludus admin, denied", user_id)
        return None

    if not _proxmox_password_valid(proxmox_username, password, settings):
        return None

    return LudusIdentity(
        user_id=user_id, proxmox_username=proxmox_username, is_admin=is_admin
    )


__all__ = ["LudusIdentity", "authenticate_ludus"]
