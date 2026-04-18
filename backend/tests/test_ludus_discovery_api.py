"""Tests for the /api/ludus discovery endpoints (list ranges, fetch config)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ludus import router as ludus_router
from app.core.config import Settings, get_settings
from app.core.deps import get_current_user, get_ludus_client_registry
from app.models.user import User
from app.services.exceptions import LudusError, LudusNotFound
from app.services.ludus import LudusClient


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email="instructor@example.com",
        admin_password="super-secret-test-pw",
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key",
        _env_file=None,
    )


@pytest.fixture
def fake_admin() -> User:
    return User(
        email="instructor@example.com",
        password_hash="irrelevant-for-these-tests",
        role="instructor",
    )


@pytest.fixture
def mock_ludus() -> MagicMock:
    return MagicMock(spec=LudusClient)


class _MockRegistry:
    """Wrap a MagicMock so it quacks like ``LudusClientRegistry``."""

    def __init__(self, mock: MagicMock) -> None:
        self._mock = mock

    def get(self, name: str = "default") -> MagicMock:
        if name != "default":
            raise ValueError(f"Unknown Ludus server '{name}'")
        return self._mock

    @property
    def server_names(self) -> list[str]:
        return ["default"]


def _build_app(
    settings: Settings,
    mock_ludus: MagicMock,
    current_user: User | None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(ludus_router)

    def _override_get_settings() -> Settings:
        return settings

    registry = _MockRegistry(mock_ludus)

    app.dependency_overrides[get_settings] = _override_get_settings
    app.dependency_overrides[get_ludus_client_registry] = lambda: registry

    if current_user is not None:

        def _override_get_current_user() -> User:
            return current_user

        app.dependency_overrides[get_current_user] = _override_get_current_user

    return app


@pytest.fixture
def client(
    settings: Settings,
    mock_ludus: MagicMock,
    fake_admin: User,
) -> Iterator[TestClient]:
    app = _build_app(settings, mock_ludus, fake_admin)
    with TestClient(app) as tc:
        yield tc


@pytest.fixture
def anon_client(
    settings: Settings,
    mock_ludus: MagicMock,
) -> Iterator[TestClient]:
    app = _build_app(settings, mock_ludus, current_user=None)
    with TestClient(app) as tc:
        yield tc


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_list_ranges_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/ranges")
    assert resp.status_code == 401


def test_get_config_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/ranges/1/config")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/ludus/ranges
# ---------------------------------------------------------------------------


def test_list_ranges_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_list.return_value = [
        {
            "rangeID": "RZ",
            "rangeNumber": 1,
            "name": "Alice Range",
            "numberOfVMs": 3,
            "rangeState": "DEPLOYED",
        },
        {"rangeID": "RZ2", "rangeNumber": 2, "name": "Bob Range"},
    ]

    resp = client.get("/api/ludus/ranges")
    assert resp.status_code == 200
    body = resp.json()
    assert "ranges" in body
    assert len(body["ranges"]) == 2
    assert body["ranges"][0]["rangeID"] == "RZ"
    assert body["ranges"][0]["numberOfVMs"] == 3
    assert body["ranges"][0]["rangeState"] == "DEPLOYED"
    assert body["ranges"][1]["rangeID"] == "RZ2"


def test_list_ranges_empty(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_list.return_value = []

    resp = client.get("/api/ludus/ranges")
    assert resp.status_code == 200
    assert resp.json()["ranges"] == []


def test_list_ranges_ludus_error_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_list.side_effect = LudusError("connection refused", status_code=503)

    resp = client.get("/api/ludus/ranges")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/ludus/ranges/{user_id}/config
# ---------------------------------------------------------------------------


RANGE_YAML = "ludus:\n  - vm_name: test\n"


def test_get_range_config_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_get_config.return_value = RANGE_YAML

    resp = client.get("/api/ludus/ranges/1/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["range_number"] == 1
    assert body["config_yaml"] == RANGE_YAML
    mock_ludus.range_get_config.assert_called_once_with(range_number=1)


def test_get_range_config_not_found_returns_404(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_get_config.side_effect = LudusNotFound("range not found", status_code=404)

    resp = client.get("/api/ludus/ranges/999/config")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_range_config_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.range_get_config.side_effect = LudusError("internal error", status_code=500)

    resp = client.get("/api/ludus/ranges/1/config")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/ludus/users
# ---------------------------------------------------------------------------


def test_list_users_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.user_list.return_value = [
        {"userID": "alice", "name": "Alice"},
        {"userID": "bob", "name": "Bob"},
    ]

    resp = client.get("/api/ludus/users")
    assert resp.status_code == 200
    body = resp.json()
    assert "users" in body
    assert len(body["users"]) == 2
    assert body["users"][0]["userID"] == "alice"


def test_list_users_ludus_error_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.user_list.side_effect = LudusError("connection refused", status_code=503)

    resp = client.get("/api/ludus/users")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_list_users_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/users")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/ranges/{range_number}/deploy
# ---------------------------------------------------------------------------


def test_deploy_range_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_deploy_existing.return_value = None

    resp = client.post("/api/ludus/ranges/1/deploy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Deployment started"
    mock_ludus.range_deploy_existing.assert_called_once_with(range_number=1)


def test_deploy_range_not_found_returns_404(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_deploy_existing.side_effect = LudusNotFound("range not found", status_code=404)

    resp = client.post("/api/ludus/ranges/999/deploy")
    assert resp.status_code == 404


def test_deploy_range_ludus_error_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_deploy_existing.side_effect = LudusError("internal error", status_code=500)

    resp = client.post("/api/ludus/ranges/1/deploy")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/ludus/ranges/{range_number}
# ---------------------------------------------------------------------------


def test_destroy_range_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_destroy.return_value = None

    resp = client.delete("/api/ludus/ranges/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Range destroyed"
    mock_ludus.range_destroy.assert_called_once_with(1)


def test_destroy_range_not_found_returns_404(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_destroy.side_effect = LudusNotFound("range not found", status_code=404)

    resp = client.delete("/api/ludus/ranges/999")
    assert resp.status_code == 404


def test_destroy_range_ludus_error_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_destroy.side_effect = LudusError("internal error", status_code=500)

    resp = client.delete("/api/ludus/ranges/1")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]
