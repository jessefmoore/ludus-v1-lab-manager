"""Tests for /api/ludus/ansible endpoints (roles, collections, subscriptions)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ludus_ansible import router as ansible_router
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
    app.include_router(ansible_router)

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
# GET /api/ludus/ansible/subscription-roles
# ---------------------------------------------------------------------------


def test_list_subscription_roles_success(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_subscription_roles.return_value = [
        {"name": "role1", "description": "First role"},
        {"name": "role2", "description": "Second role"},
    ]

    resp = client.get("/api/ludus/ansible/subscription-roles")
    assert resp.status_code == 200
    body = resp.json()
    assert "roles" in body
    assert len(body["roles"]) == 2
    assert body["roles"][0]["name"] == "role1"


def test_list_subscription_roles_empty(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_subscription_roles.return_value = []

    resp = client.get("/api/ludus/ansible/subscription-roles")
    assert resp.status_code == 200
    assert resp.json()["roles"] == []


def test_list_subscription_roles_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_subscription_roles.side_effect = LudusError(
        "connection refused", status_code=503
    )

    resp = client.get("/api/ludus/ansible/subscription-roles")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_list_subscription_roles_without_auth_returns_401(
    anon_client: TestClient,
) -> None:
    resp = anon_client.get("/api/ludus/ansible/subscription-roles")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/ansible/subscription-roles
# ---------------------------------------------------------------------------


def test_install_subscription_roles_success(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_install_subscription_roles.return_value = None

    resp = client.post(
        "/api/ludus/ansible/subscription-roles",
        json={"roles": ["role1"], "global_": False, "force": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Subscription roles installed"
    mock_ludus.ansible_install_subscription_roles.assert_called_once_with(
        ["role1"], global_=False, force=False
    )


def test_install_subscription_roles_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_install_subscription_roles.side_effect = LudusError(
        "internal", status_code=500
    )

    resp = client.post(
        "/api/ludus/ansible/subscription-roles",
        json={"roles": ["role1"]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_install_subscription_roles_without_auth_returns_401(
    anon_client: TestClient,
) -> None:
    resp = anon_client.post(
        "/api/ludus/ansible/subscription-roles",
        json={"roles": ["role1"]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/ansible/role/vars
# ---------------------------------------------------------------------------


def test_get_role_vars_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.ansible_role_vars.return_value = [
        {"name": "var1", "default": "value1", "description": "First var"},
    ]

    resp = client.post(
        "/api/ludus/ansible/role/vars",
        json={"roles": ["role1"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "vars" in body
    assert len(body["vars"]) == 1
    assert body["vars"][0]["name"] == "var1"
    mock_ludus.ansible_role_vars.assert_called_once_with(["role1"])


def test_get_role_vars_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role_vars.side_effect = LudusNotFound(
        "role not found", status_code=404
    )

    resp = client.post(
        "/api/ludus/ansible/role/vars",
        json={"roles": ["nonexistent"]},
    )
    assert resp.status_code == 404


def test_get_role_vars_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role_vars.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/ansible/role/vars",
        json={"roles": ["role1"]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_get_role_vars_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/ansible/role/vars",
        json={"roles": ["role1"]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/ludus/ansible
# ---------------------------------------------------------------------------


def test_list_installed_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.ansible_list.return_value = [
        {"name": "my-role", "version": "1.0.0", "scope": "user", "type": "role"},
    ]

    resp = client.get("/api/ludus/ansible")
    assert resp.status_code == 200
    body = resp.json()
    assert "roles" in body
    assert len(body["roles"]) == 1
    assert body["roles"][0]["name"] == "my-role"
    mock_ludus.ansible_list.assert_called_once_with(user_id=None)


def test_list_installed_with_user_id(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_list.return_value = []

    resp = client.get("/api/ludus/ansible", params={"user_id": "alice"})
    assert resp.status_code == 200
    mock_ludus.ansible_list.assert_called_once_with(user_id="alice")


def test_list_installed_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_list.side_effect = LudusError(
        "connection refused", status_code=503
    )

    resp = client.get("/api/ludus/ansible")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_list_installed_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/ansible")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/ludus/ansible/role/scope
# ---------------------------------------------------------------------------


def test_change_role_scope_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.ansible_role_scope.return_value = None

    resp = client.patch(
        "/api/ludus/ansible/role/scope",
        json={"roles": ["role1"], "global_": False, "copy": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Role scope updated"
    mock_ludus.ansible_role_scope.assert_called_once_with(
        ["role1"], global_=False, copy=False
    )


def test_change_role_scope_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role_scope.side_effect = LudusNotFound(
        "role not found", status_code=404
    )

    resp = client.patch(
        "/api/ludus/ansible/role/scope",
        json={"roles": ["nonexistent"]},
    )
    assert resp.status_code == 404


def test_change_role_scope_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role_scope.side_effect = LudusError("internal", status_code=500)

    resp = client.patch(
        "/api/ludus/ansible/role/scope",
        json={"roles": ["role1"]},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_change_role_scope_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.patch(
        "/api/ludus/ansible/role/scope",
        json={"roles": ["role1"]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/ansible/role
# ---------------------------------------------------------------------------


def test_manage_role_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.ansible_role.return_value = None

    resp = client.post(
        "/api/ludus/ansible/role",
        json={"role": "my-role", "action": "install"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Role install completed"
    mock_ludus.ansible_role.assert_called_once_with(
        "my-role", "install", version=None, force=False, global_=False
    )


def test_manage_role_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role.side_effect = LudusNotFound(
        "role not found", status_code=404
    )

    resp = client.post(
        "/api/ludus/ansible/role",
        json={"role": "nonexistent", "action": "remove"},
    )
    assert resp.status_code == 404


def test_manage_role_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/ansible/role",
        json={"role": "my-role", "action": "install"},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_manage_role_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/ansible/role",
        json={"role": "my-role", "action": "install"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /api/ludus/ansible/role/fromtar
# ---------------------------------------------------------------------------


def test_install_role_from_tar_success(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role_from_tar.return_value = None

    resp = client.put(
        "/api/ludus/ansible/role/fromtar",
        files={"file": ("role.tar.gz", b"fake-tar-data", "application/gzip")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Role installed from tar"
    mock_ludus.ansible_role_from_tar.assert_called_once_with(
        b"fake-tar-data", "role.tar.gz", force=False
    )


def test_install_role_from_tar_with_force(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role_from_tar.return_value = None

    resp = client.put(
        "/api/ludus/ansible/role/fromtar",
        files={"file": ("role.tar.gz", b"fake-tar-data", "application/gzip")},
        params={"force": "true"},
    )
    assert resp.status_code == 200
    mock_ludus.ansible_role_from_tar.assert_called_once_with(
        b"fake-tar-data", "role.tar.gz", force=True
    )


def test_install_role_from_tar_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_role_from_tar.side_effect = LudusError(
        "internal", status_code=500
    )

    resp = client.put(
        "/api/ludus/ansible/role/fromtar",
        files={"file": ("role.tar.gz", b"fake-tar-data", "application/gzip")},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_install_role_from_tar_without_auth_returns_401(
    anon_client: TestClient,
) -> None:
    resp = anon_client.put(
        "/api/ludus/ansible/role/fromtar",
        files={"file": ("role.tar.gz", b"fake-tar-data", "application/gzip")},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/ansible/collection
# ---------------------------------------------------------------------------


def test_install_collection_success(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_collection.return_value = None

    resp = client.post(
        "/api/ludus/ansible/collection",
        json={"collection": "my.collection"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Collection installed"
    mock_ludus.ansible_collection.assert_called_once_with(
        "my.collection", version=None, force=False
    )


def test_install_collection_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_collection.side_effect = LudusNotFound(
        "collection not found", status_code=404
    )

    resp = client.post(
        "/api/ludus/ansible/collection",
        json={"collection": "nonexistent.collection"},
    )
    assert resp.status_code == 404


def test_install_collection_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.ansible_collection.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/ansible/collection",
        json={"collection": "my.collection"},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_install_collection_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/ansible/collection",
        json={"collection": "my.collection"},
    )
    assert resp.status_code == 401
