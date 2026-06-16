"""Tests for /api/ludus/testing endpoints (testing mode, allow/deny, update)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ludus_testing import router as testing_router
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
    app.include_router(testing_router)

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
# PUT /api/ludus/testing/start
# ---------------------------------------------------------------------------


def test_testing_start_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.testing_start.return_value = None

    resp = client.put(
        "/api/ludus/testing/start",
        json={"range_id": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Testing mode started"
    mock_ludus.testing_start.assert_called_once_with(range_id=1, user_id=None)


def test_testing_start_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_start.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.put(
        "/api/ludus/testing/start",
        json={"range_id": 999},
    )
    assert resp.status_code == 404


def test_testing_start_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_start.side_effect = LudusError("internal", status_code=500)

    resp = client.put(
        "/api/ludus/testing/start",
        json={"range_id": 1},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_testing_start_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.put(
        "/api/ludus/testing/start",
        json={"range_id": 1},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/ludus/testing/stop
# ---------------------------------------------------------------------------


def test_testing_stop_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.testing_stop.return_value = None

    resp = client.put(
        "/api/ludus/testing/stop",
        json={"range_id": 1, "force": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Testing mode stopped"
    mock_ludus.testing_stop.assert_called_once_with(
        range_id=1, user_id=None, force=True
    )


def test_testing_stop_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_stop.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.put(
        "/api/ludus/testing/stop",
        json={"range_id": 999},
    )
    assert resp.status_code == 404


def test_testing_stop_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_stop.side_effect = LudusError("internal", status_code=500)

    resp = client.put(
        "/api/ludus/testing/stop",
        json={"range_id": 1},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_testing_stop_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.put(
        "/api/ludus/testing/stop",
        json={"range_id": 1},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/testing/allow
# ---------------------------------------------------------------------------


def test_testing_allow_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.testing_allow.return_value = {
        "result": "ok",
        "domains": ["example.com"],
    }

    resp = client.post(
        "/api/ludus/testing/allow",
        json={"range_id": 1, "domains": ["example.com"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "ok"
    assert body["domains"] == ["example.com"]
    mock_ludus.testing_allow.assert_called_once_with(
        range_id=1, user_id=None, domains=["example.com"], ips=None
    )


def test_testing_allow_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_allow.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.post(
        "/api/ludus/testing/allow",
        json={"range_id": 999, "domains": ["example.com"]},
    )
    assert resp.status_code == 404


def test_testing_allow_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_allow.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/testing/allow",
        json={"range_id": 1, "domains": ["example.com"]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_testing_allow_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/testing/allow",
        json={"range_id": 1, "domains": ["example.com"]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/testing/deny
# ---------------------------------------------------------------------------


def test_testing_deny_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.testing_deny.return_value = {
        "result": "ok",
        "domains": ["example.com"],
    }

    resp = client.post(
        "/api/ludus/testing/deny",
        json={"range_id": 1, "ips": ["1.2.3.4"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "ok"
    mock_ludus.testing_deny.assert_called_once_with(
        range_id=1, user_id=None, domains=None, ips=["1.2.3.4"]
    )


def test_testing_deny_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_deny.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.post(
        "/api/ludus/testing/deny",
        json={"range_id": 999, "ips": ["1.2.3.4"]},
    )
    assert resp.status_code == 404


def test_testing_deny_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_deny.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/testing/deny",
        json={"range_id": 1, "ips": ["1.2.3.4"]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_testing_deny_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/testing/deny",
        json={"range_id": 1, "ips": ["1.2.3.4"]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/testing/update
# ---------------------------------------------------------------------------


def test_testing_update_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.testing_update.return_value = None

    resp = client.post(
        "/api/ludus/testing/update",
        json={"name": "test-config", "range_id": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Testing config updated"
    mock_ludus.testing_update.assert_called_once_with(
        "test-config", range_id=1, user_id=None
    )


def test_testing_update_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_update.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.post(
        "/api/ludus/testing/update",
        json={"name": "test-config", "range_id": 999},
    )
    assert resp.status_code == 404


def test_testing_update_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.testing_update.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/testing/update",
        json={"name": "test-config", "range_id": 1},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_testing_update_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/testing/update",
        json={"name": "test-config", "range_id": 1},
    )
    assert resp.status_code == 401
