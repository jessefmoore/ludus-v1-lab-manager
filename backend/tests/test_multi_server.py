"""Tests for multi-Ludus-server support.

Covers:
- ``Settings.ludus_servers`` env-var discovery
- ``LudusClientRegistry`` construction and error handling
- API endpoint ``?server=`` param routing
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ludus import router as ludus_router
from app.api.settings import router as settings_router
from app.core.config import LudusServerConfig, Settings, get_settings
from app.core.deps import (
    LudusClientRegistry,
    get_current_user,
    get_ludus_client_registry,
)
from app.models.user import User
from app.services.ludus import LudusClient

# ---------------------------------------------------------------------------
# Settings.ludus_servers tests
# ---------------------------------------------------------------------------


def test_ludus_servers_includes_default_only_when_no_extra_env() -> None:
    """With no extra LUDUS_*_URL env vars, only ``default`` is returned."""
    s = Settings(
        app_env="testing",
        app_secret_key="test-secret",
        admin_email="admin@test.com",
        admin_password="test-password",
        ludus_default_url="https://ludus-default.test",
        ludus_default_api_key="default-key",
        ludus_default_verify_tls=False,
        _env_file=None,
    )
    servers = s.ludus_servers
    assert "default" in servers
    assert servers["default"].url == "https://ludus-default.test"
    assert servers["default"].api_key == "default-key"
    assert servers["default"].verify_tls is False
    assert len(servers) == 1


def test_ludus_servers_discovers_extra_server_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setting LUDUS_RESEARCH_URL + LUDUS_RESEARCH_API_KEY adds a ``research`` entry."""
    monkeypatch.setenv("LUDUS_RESEARCH_URL", "https://ludus-research.test:9090")
    monkeypatch.setenv("LUDUS_RESEARCH_API_KEY", "research-key-abc")
    monkeypatch.setenv("LUDUS_RESEARCH_VERIFY_TLS", "true")

    s = Settings(
        app_env="testing",
        app_secret_key="test-secret",
        admin_email="admin@test.com",
        admin_password="test-password",
        ludus_default_url="https://ludus-default.test",
        ludus_default_api_key="default-key",
        _env_file=None,
    )
    servers = s.ludus_servers
    assert "default" in servers
    assert "research" in servers
    assert servers["research"].url == "https://ludus-research.test:9090"
    assert servers["research"].api_key == "research-key-abc"
    assert servers["research"].verify_tls is True


def test_ludus_servers_skips_incomplete_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """If LUDUS_LAB_URL is set but LUDUS_LAB_API_KEY is missing, skip it."""
    monkeypatch.setenv("LUDUS_LAB_URL", "https://lab.test")
    # intentionally NOT setting LUDUS_LAB_API_KEY

    s = Settings(
        app_env="testing",
        app_secret_key="test-secret",
        admin_email="admin@test.com",
        admin_password="test-password",
        ludus_default_url="https://ludus-default.test",
        ludus_default_api_key="default-key",
        _env_file=None,
    )
    servers = s.ludus_servers
    assert "lab" not in servers
    assert len(servers) == 1


# ---------------------------------------------------------------------------
# LudusClientRegistry tests
# ---------------------------------------------------------------------------


def test_registry_get_default_works() -> None:
    """``registry.get("default")`` returns a LudusClient."""
    servers = {
        "default": LudusServerConfig(
            name="default",
            url="https://ludus.test",
            api_key="key",
            verify_tls=False,
        ),
    }
    registry = LudusClientRegistry(servers)
    client = registry.get("default")
    assert isinstance(client, LudusClient)
    # Second call returns the same cached instance.
    assert registry.get("default") is client
    registry.close_all()


def test_registry_get_unknown_raises_value_error() -> None:
    """``registry.get("nonexistent")`` raises ``ValueError``."""
    servers = {
        "default": LudusServerConfig(
            name="default",
            url="https://ludus.test",
            api_key="key",
        ),
    }
    registry = LudusClientRegistry(servers)
    with pytest.raises(ValueError, match="Unknown Ludus server 'nonexistent'"):
        registry.get("nonexistent")
    registry.close_all()


def test_registry_server_names_sorted() -> None:
    """``server_names`` returns a sorted list."""
    servers = {
        "zebra": LudusServerConfig(name="zebra", url="https://z.test", api_key="k"),
        "alpha": LudusServerConfig(name="alpha", url="https://a.test", api_key="k"),
        "default": LudusServerConfig(name="default", url="https://d.test", api_key="k"),
    }
    registry = LudusClientRegistry(servers)
    assert registry.server_names == ["alpha", "default", "zebra"]
    registry.close_all()


# ---------------------------------------------------------------------------
# API endpoint ?server= tests
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_admin() -> User:
    return User(
        email="instructor@example.com",
        password_hash="irrelevant",
        role="instructor",
    )


@pytest.fixture
def mock_ludus() -> MagicMock:
    return MagicMock(spec=LudusClient)


class _MockRegistry:
    """Registry that holds a single ``default`` mock client."""

    def __init__(self, mock: MagicMock) -> None:
        self._mock = mock
        self._servers = {
            "default": LudusServerConfig(
                name="default", url="https://ludus.test", api_key="key", verify_tls=False,
            ),
        }

    def get(self, name: str = "default") -> MagicMock:
        if name not in self._servers:
            raise ValueError(
                f"Unknown Ludus server '{name}'. Configured: {', '.join(sorted(self._servers))}"
            )
        return self._mock

    @property
    def server_names(self) -> list[str]:
        return sorted(self._servers)

    @property
    def servers(self) -> dict[str, LudusServerConfig]:
        return self._servers


def _build_app(
    mock_ludus: MagicMock,
    current_user: User,
) -> FastAPI:
    app = FastAPI()
    app.include_router(ludus_router)
    app.include_router(settings_router)

    settings = Settings(
        app_env="testing",
        app_secret_key="test-secret",
        admin_email="admin@test.com",
        admin_password="test-password",
        ludus_default_url="https://ludus.test",
        ludus_default_api_key="key",
        _env_file=None,
    )
    registry = _MockRegistry(mock_ludus)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_ludus_client_registry] = lambda: registry
    app.dependency_overrides[get_current_user] = lambda: current_user
    return app


@pytest.fixture
def client(mock_ludus: MagicMock, fake_admin: User) -> Iterator[TestClient]:
    app = _build_app(mock_ludus, fake_admin)
    with TestClient(app) as tc:
        yield tc


def test_ranges_with_default_server_works(
    client: TestClient,
    mock_ludus: MagicMock,
) -> None:
    mock_ludus.range_list.return_value = []
    resp = client.get("/api/ludus/ranges?server=default")
    assert resp.status_code == 200
    mock_ludus.range_list.assert_called_once()


def test_ranges_with_unknown_server_returns_400(client: TestClient) -> None:
    resp = client.get("/api/ludus/ranges?server=nonexistent")
    assert resp.status_code == 400
    assert "Unknown Ludus server" in resp.json()["detail"]


def test_templates_with_unknown_server_returns_400(client: TestClient) -> None:
    resp = client.get("/api/ludus/templates?server=nonexistent")
    assert resp.status_code == 400


def test_test_ludus_with_unknown_server_returns_400(client: TestClient) -> None:
    resp = client.post("/api/settings/test-ludus?server=nonexistent")
    assert resp.status_code == 400


def test_ludus_servers_endpoint(client: TestClient) -> None:
    resp = client.get("/api/settings/ludus-servers")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["servers"]) == 1
    assert body["servers"][0]["name"] == "default"
    assert "****" in body["servers"][0]["api_key_masked"]


def test_ranges_omitting_server_defaults_to_default(
    client: TestClient,
    mock_ludus: MagicMock,
) -> None:
    """Not passing ``?server`` uses ``"default"``."""
    mock_ludus.range_list.return_value = []
    resp = client.get("/api/ludus/ranges")
    assert resp.status_code == 200
    mock_ludus.range_list.assert_called_once()
