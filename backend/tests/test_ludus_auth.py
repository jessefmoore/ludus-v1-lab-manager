"""Tests for Ludus/Proxmox login authentication."""

from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.services import ludus_auth
from app.services.ludus_auth import authenticate_ludus

USERS = [
    {"userID": "JM", "proxmoxUsername": "jesse", "isAdmin": True},
    {"userID": "STU", "proxmoxUsername": "student1", "isAdmin": False},
]


class FakeClient:
    def __init__(self, users=USERS, raise_=None):
        self._users = users
        self._raise = raise_
        self.closed = False

    def user_list(self):
        if self._raise:
            raise self._raise
        return self._users

    def close(self):
        self.closed = True


def _settings(**kw) -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="s",
        admin_email="JM",
        admin_password="p",
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="k",
        _env_file=None,
        **kw,
    )


@pytest.fixture
def proxmox_ok(monkeypatch):
    """Patch the Proxmox ticket call: a ticket is issued only for password 'right'."""

    def fake_post(url, data=None, **kwargs):
        good = (data or {}).get("password") == "right"
        return httpx.Response(
            200 if good else 401,
            json={"data": {"ticket": "TICKET"}} if good else {"data": None},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(ludus_auth.httpx, "post", fake_post)


def test_admin_valid(proxmox_ok) -> None:
    ident = authenticate_ludus("JM", "right", _settings(), ludus_client=FakeClient())
    assert ident is not None
    assert ident.user_id == "JM" and ident.proxmox_username == "jesse" and ident.is_admin


def test_login_by_proxmox_username(proxmox_ok) -> None:
    ident = authenticate_ludus("jesse", "right", _settings(), ludus_client=FakeClient())
    assert ident is not None and ident.user_id == "JM"


def test_bad_password(proxmox_ok) -> None:
    assert authenticate_ludus("JM", "wrong", _settings(), ludus_client=FakeClient()) is None


def test_unknown_user(proxmox_ok) -> None:
    assert authenticate_ludus("ghost", "right", _settings(), ludus_client=FakeClient()) is None


def test_non_admin_denied_by_default(proxmox_ok) -> None:
    assert authenticate_ludus("STU", "right", _settings(), ludus_client=FakeClient()) is None


def test_non_admin_allowed_when_configured(proxmox_ok) -> None:
    ident = authenticate_ludus(
        "STU", "right", _settings(ludus_auth_admins_only=False), ludus_client=FakeClient()
    )
    assert ident is not None and ident.user_id == "STU" and not ident.is_admin


def test_disabled_returns_none() -> None:
    assert (
        authenticate_ludus(
            "JM", "right", _settings(ludus_auth_enabled=False), ludus_client=FakeClient()
        )
        is None
    )


def test_ludus_unreachable_returns_none(proxmox_ok) -> None:
    client = FakeClient(raise_=RuntimeError("ludus down"))
    assert authenticate_ludus("JM", "right", _settings(), ludus_client=client) is None


def test_proxmox_unreachable_returns_none(monkeypatch) -> None:
    def boom(url, **kwargs):
        raise httpx.ConnectError("no route", request=httpx.Request("POST", url))

    monkeypatch.setattr(ludus_auth.httpx, "post", boom)
    assert authenticate_ludus("JM", "right", _settings(), ludus_client=FakeClient()) is None


def test_resolved_proxmox_url_derives_from_ludus_host() -> None:
    assert _settings().resolved_proxmox_url == "https://ludus.test:8006"
    assert (
        _settings(proxmox_url="https://px.example:8006/").resolved_proxmox_url
        == "https://px.example:8006"
    )
