"""Tests for /api/ludus/groups endpoints (group CRUD, user/range membership)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ludus_groups import router as groups_router
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
    app.include_router(groups_router)

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
# GET /api/ludus/groups
# ---------------------------------------------------------------------------


def test_list_groups_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_list.return_value = [
        {"name": "test-group", "description": "A test group"},
        {"name": "dev-group", "description": "Dev team"},
    ]

    resp = client.get("/api/ludus/groups")
    assert resp.status_code == 200
    body = resp.json()
    assert "groups" in body
    assert len(body["groups"]) == 2
    assert body["groups"][0]["name"] == "test-group"


def test_list_groups_empty(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_list.return_value = []

    resp = client.get("/api/ludus/groups")
    assert resp.status_code == 200
    assert resp.json()["groups"] == []


def test_list_groups_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_list.side_effect = LudusError("connection refused", status_code=503)

    resp = client.get("/api/ludus/groups")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_list_groups_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/groups")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/groups
# ---------------------------------------------------------------------------


def test_create_group_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_create.return_value = None

    resp = client.post(
        "/api/ludus/groups",
        json={"name": "test-group", "description": "Test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Group created"
    mock_ludus.group_create.assert_called_once_with("test-group", description="Test")


def test_create_group_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_create.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/groups",
        json={"name": "test-group", "description": "Test"},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_create_group_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/groups",
        json={"name": "test-group", "description": "Test"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/ludus/groups/{group_name}
# ---------------------------------------------------------------------------


def test_delete_group_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_delete.return_value = None

    resp = client.delete("/api/ludus/groups/test-group")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Group deleted"
    mock_ludus.group_delete.assert_called_once_with("test-group")


def test_delete_group_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_delete.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.delete("/api/ludus/groups/nonexistent")
    assert resp.status_code == 404


def test_delete_group_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_delete.side_effect = LudusError("internal", status_code=500)

    resp = client.delete("/api/ludus/groups/test-group")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_delete_group_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.delete("/api/ludus/groups/test-group")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/ludus/groups/{group_name}/users
# ---------------------------------------------------------------------------


def test_get_group_users_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_users.return_value = [
        {"userID": "alice", "name": "Alice", "manager": False},
        {"userID": "bob", "name": "Bob", "manager": True},
    ]

    resp = client.get("/api/ludus/groups/test-group/users")
    assert resp.status_code == 200
    body = resp.json()
    assert "users" in body
    assert len(body["users"]) == 2
    assert body["users"][0]["userID"] == "alice"
    mock_ludus.group_users.assert_called_once_with("test-group")


def test_get_group_users_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_users.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.get("/api/ludus/groups/nonexistent/users")
    assert resp.status_code == 404


def test_get_group_users_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_users.side_effect = LudusError("internal", status_code=500)

    resp = client.get("/api/ludus/groups/test-group/users")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_get_group_users_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/groups/test-group/users")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/groups/{group_name}/users
# ---------------------------------------------------------------------------


def test_add_group_users_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_add_users.return_value = {"result": "ok"}

    resp = client.post(
        "/api/ludus/groups/test-group/users",
        json={"user_ids": ["alice"], "managers": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "ok"
    mock_ludus.group_add_users.assert_called_once_with(
        "test-group", ["alice"], managers=False
    )


def test_add_group_users_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_add_users.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.post(
        "/api/ludus/groups/nonexistent/users",
        json={"user_ids": ["alice"], "managers": False},
    )
    assert resp.status_code == 404


def test_add_group_users_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_add_users.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/groups/test-group/users",
        json={"user_ids": ["alice"], "managers": False},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_add_group_users_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/groups/test-group/users",
        json={"user_ids": ["alice"], "managers": False},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/ludus/groups/{group_name}/users
# ---------------------------------------------------------------------------


def test_remove_group_users_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_remove_users.return_value = {"result": "ok"}

    resp = client.request(
        "DELETE",
        "/api/ludus/groups/test-group/users",
        json={"user_ids": ["alice"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "ok"
    mock_ludus.group_remove_users.assert_called_once_with("test-group", ["alice"])


def test_remove_group_users_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_remove_users.side_effect = LudusNotFound(
        "not found", status_code=404
    )

    resp = client.request(
        "DELETE",
        "/api/ludus/groups/nonexistent/users",
        json={"user_ids": ["alice"]},
    )
    assert resp.status_code == 404


def test_remove_group_users_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_remove_users.side_effect = LudusError("internal", status_code=500)

    resp = client.request(
        "DELETE",
        "/api/ludus/groups/test-group/users",
        json={"user_ids": ["alice"]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_remove_group_users_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.request(
        "DELETE",
        "/api/ludus/groups/test-group/users",
        json={"user_ids": ["alice"]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/ludus/groups/{group_name}/ranges
# ---------------------------------------------------------------------------


def test_get_group_ranges_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_ranges.return_value = [
        {"rangeID": "r1", "rangeNumber": 1, "name": "range-1"},
    ]

    resp = client.get("/api/ludus/groups/test-group/ranges")
    assert resp.status_code == 200
    body = resp.json()
    assert "ranges" in body
    assert len(body["ranges"]) == 1
    assert body["ranges"][0]["rangeNumber"] == 1
    mock_ludus.group_ranges.assert_called_once_with("test-group")


def test_get_group_ranges_empty(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_ranges.return_value = []

    resp = client.get("/api/ludus/groups/test-group/ranges")
    assert resp.status_code == 200
    assert resp.json()["ranges"] == []


def test_get_group_ranges_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_ranges.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.get("/api/ludus/groups/nonexistent/ranges")
    assert resp.status_code == 404


def test_get_group_ranges_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_ranges.side_effect = LudusError("internal", status_code=500)

    resp = client.get("/api/ludus/groups/test-group/ranges")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_get_group_ranges_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/groups/test-group/ranges")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/groups/{group_name}/ranges
# ---------------------------------------------------------------------------


def test_add_group_ranges_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_add_ranges.return_value = {"result": "ok"}

    resp = client.post(
        "/api/ludus/groups/test-group/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "ok"
    mock_ludus.group_add_ranges.assert_called_once_with("test-group", [1])


def test_add_group_ranges_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_add_ranges.side_effect = LudusNotFound(
        "not found", status_code=404
    )

    resp = client.post(
        "/api/ludus/groups/nonexistent/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 404


def test_add_group_ranges_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_add_ranges.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/groups/test-group/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_add_group_ranges_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/groups/test-group/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/ludus/groups/{group_name}/ranges
# ---------------------------------------------------------------------------


def test_remove_group_ranges_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.group_remove_ranges.return_value = {"result": "ok"}

    resp = client.request(
        "DELETE",
        "/api/ludus/groups/test-group/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] == "ok"
    mock_ludus.group_remove_ranges.assert_called_once_with("test-group", [1])


def test_remove_group_ranges_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_remove_ranges.side_effect = LudusNotFound(
        "not found", status_code=404
    )

    resp = client.request(
        "DELETE",
        "/api/ludus/groups/nonexistent/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 404


def test_remove_group_ranges_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.group_remove_ranges.side_effect = LudusError("internal", status_code=500)

    resp = client.request(
        "DELETE",
        "/api/ludus/groups/test-group/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_remove_group_ranges_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.request(
        "DELETE",
        "/api/ludus/groups/test-group/ranges",
        json={"range_ids": [1]},
    )
    assert resp.status_code == 401
