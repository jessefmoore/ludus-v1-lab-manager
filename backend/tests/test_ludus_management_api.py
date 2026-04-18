"""Tests for /api/ludus management endpoints (power, snapshots, templates)."""

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
from app.services.exceptions import LudusAuthError, LudusError, LudusNotFound, LudusUserExists
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
# POST /api/ludus/ranges/{range_number}/power-on
# ---------------------------------------------------------------------------


def test_power_on_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_power_on.return_value = None

    resp = client.post(
        "/api/ludus/ranges/1/power-on",
        json={"user_id": "alice", "machines": ["all"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Power on initiated"
    mock_ludus.range_power_on.assert_called_once_with("alice", machines=["all"])


def test_power_on_specific_machines(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_power_on.return_value = None

    resp = client.post(
        "/api/ludus/ranges/1/power-on",
        json={"user_id": "alice", "machines": ["web", "db"]},
    )
    assert resp.status_code == 200
    mock_ludus.range_power_on.assert_called_once_with("alice", machines=["web", "db"])


def test_power_on_not_found_returns_404(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_power_on.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.post(
        "/api/ludus/ranges/999/power-on",
        json={"user_id": "ghost"},
    )
    assert resp.status_code == 404


def test_power_on_ludus_error_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_power_on.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/ranges/1/power-on",
        json={"user_id": "alice"},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_power_on_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/ranges/1/power-on",
        json={"user_id": "alice"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/ranges/{range_number}/power-off
# ---------------------------------------------------------------------------


def test_power_off_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_power_off.return_value = None

    resp = client.post(
        "/api/ludus/ranges/1/power-off",
        json={"user_id": "alice"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Power off initiated"


def test_power_off_not_found_returns_404(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.range_power_off.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.post(
        "/api/ludus/ranges/999/power-off",
        json={"user_id": "ghost"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/ludus/snapshots
# ---------------------------------------------------------------------------


def test_list_snapshots_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_list.return_value = [
        {"name": "ctf-initial", "description": "Clean state"},
        {"name": "checkpoint-1", "description": "After setup"},
    ]

    resp = client.get("/api/ludus/snapshots", params={"user_id": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert "snapshots" in body
    assert len(body["snapshots"]) == 2
    assert body["snapshots"][0]["name"] == "ctf-initial"


def test_list_snapshots_nested_ludus_format(client: TestClient, mock_ludus: MagicMock) -> None:
    """Ludus returns [{snapshots: [{name, vmid, vmname, ...}, ...]}]."""
    mock_ludus.snapshot_list.return_value = [
        {
            "snapshots": [
                {"name": "current", "description": "You are here!", "vmid": 104, "vmname": "RZ-router"},
                {"name": "current", "description": "You are here!", "vmid": 105, "vmname": "RZ-DC"},
                {"name": "clean", "description": "Initial", "vmid": 104, "vmname": "RZ-router"},
            ],
        },
    ]

    resp = client.get("/api/ludus/snapshots", params={"user_id": "RZ"})
    assert resp.status_code == 200
    body = resp.json()
    snapshots = body["snapshots"]
    assert len(snapshots) == 2  # deduplicated by name: "current" + "clean"
    names = {s["name"] for s in snapshots}
    assert names == {"current", "clean"}
    current = next(s for s in snapshots if s["name"] == "current")
    assert set(current["vmids"]) == {104, 105}


def test_list_snapshots_empty(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_list.return_value = []

    resp = client.get("/api/ludus/snapshots")
    assert resp.status_code == 200
    assert resp.json()["snapshots"] == []


def test_list_snapshots_not_found_returns_404(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_list.side_effect = LudusNotFound("user not found", status_code=404)

    resp = client.get("/api/ludus/snapshots", params={"user_id": "ghost"})
    assert resp.status_code == 404


def test_list_snapshots_ludus_error_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_list.side_effect = LudusError("connection refused", status_code=503)

    resp = client.get("/api/ludus/snapshots")
    assert resp.status_code == 502


def test_list_snapshots_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/snapshots")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/snapshots
# ---------------------------------------------------------------------------


def test_create_snapshot_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_create.return_value = None

    resp = client.post(
        "/api/ludus/snapshots",
        json={"user_id": "alice", "name": "my-snap", "description": "test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Snapshot creation started"
    mock_ludus.snapshot_create.assert_called_once_with(
        "alice",
        "my-snap",
        description="test",
        include_ram=False,
        vmids=None,
    )


def test_create_snapshot_not_found_returns_404(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_create.side_effect = LudusNotFound("user not found", status_code=404)

    resp = client.post(
        "/api/ludus/snapshots",
        json={"user_id": "ghost", "name": "snap1"},
    )
    assert resp.status_code == 404


def test_create_snapshot_auth_error_returns_502(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_create.side_effect = LudusAuthError("forbidden", status_code=403)

    resp = client.post(
        "/api/ludus/snapshots",
        json={"user_id": "alice", "name": "snap1"},
    )
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# POST /api/ludus/snapshots/revert
# ---------------------------------------------------------------------------


def test_revert_snapshot_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_revert.return_value = None

    resp = client.post(
        "/api/ludus/snapshots/revert",
        json={"user_id": "alice", "name": "ctf-initial"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    mock_ludus.snapshot_revert.assert_called_once_with("alice", "ctf-initial", vmids=None)


def test_revert_snapshot_with_vmids(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_revert.return_value = None

    resp = client.post(
        "/api/ludus/snapshots/revert",
        json={"user_id": "alice", "name": "ctf-initial", "vmids": [100, 101]},
    )
    assert resp.status_code == 200
    mock_ludus.snapshot_revert.assert_called_once_with("alice", "ctf-initial", vmids=[100, 101])


def test_revert_snapshot_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.snapshot_revert.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.post(
        "/api/ludus/snapshots/revert",
        json={"user_id": "alice", "name": "nope"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/ludus/snapshots/{name}
# ---------------------------------------------------------------------------


def test_delete_snapshot_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.snapshot_delete.return_value = None

    resp = client.delete("/api/ludus/snapshots/old-snap", params={"user_id": "alice"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    mock_ludus.snapshot_delete.assert_called_once_with("alice", "old-snap")


def test_delete_snapshot_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.snapshot_delete.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.delete("/api/ludus/snapshots/nope", params={"user_id": "alice"})
    assert resp.status_code == 404


def test_delete_snapshot_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.snapshot_delete.side_effect = LudusError("internal", status_code=500)

    resp = client.delete("/api/ludus/snapshots/old-snap", params={"user_id": "alice"})
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# GET /api/ludus/templates
# ---------------------------------------------------------------------------


def test_list_templates_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.template_list.return_value = [
        {"name": "debian-12-x64-server-template", "os": "Debian 12"},
        {"name": "win11-22h2-x64-enterprise-template", "os": "Windows 11"},
    ]

    resp = client.get("/api/ludus/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert "templates" in body
    assert len(body["templates"]) == 2
    assert body["templates"][0]["name"] == "debian-12-x64-server-template"


def test_list_templates_empty(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.template_list.return_value = []

    resp = client.get("/api/ludus/templates")
    assert resp.status_code == 200
    assert resp.json()["templates"] == []


def test_list_templates_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.template_list.side_effect = LudusError("connection refused", status_code=503)

    resp = client.get("/api/ludus/templates")
    assert resp.status_code == 502


def test_list_templates_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/templates")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/ludus/templates/{name}
# ---------------------------------------------------------------------------


def test_delete_template_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.template_delete.return_value = None

    resp = client.delete("/api/ludus/templates/debian-12-x64-server-template")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "Template deleted"
    mock_ludus.template_delete.assert_called_once_with("debian-12-x64-server-template")


def test_delete_template_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.template_delete.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.delete("/api/ludus/templates/nope")
    assert resp.status_code == 404


def test_delete_template_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.template_delete.side_effect = LudusError("internal", status_code=500)

    resp = client.delete("/api/ludus/templates/some-template")
    assert resp.status_code == 502


def test_delete_template_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.delete("/api/ludus/templates/some-template")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/ludus/users  (create user)
# ---------------------------------------------------------------------------


def test_create_user_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.user_add.return_value = {"userID": "alice", "apiKey": "key123"}

    resp = client.post(
        "/api/ludus/users",
        json={"user_id": "alice", "name": "Alice", "email": "alice@example.com"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["userID"] == "alice"
    assert body["apiKey"] == "key123"
    mock_ludus.user_add.assert_called_once_with("alice", "Alice", "alice@example.com")


def test_create_user_already_exists_returns_409(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.user_add.side_effect = LudusUserExists("already exists", status_code=409)

    resp = client.post(
        "/api/ludus/users",
        json={"user_id": "alice", "name": "Alice", "email": "alice@example.com"},
    )
    assert resp.status_code == 409


def test_create_user_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.user_add.side_effect = LudusError("internal", status_code=500)

    resp = client.post(
        "/api/ludus/users",
        json={"user_id": "alice", "name": "Alice", "email": "alice@example.com"},
    )
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_create_user_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.post(
        "/api/ludus/users",
        json={"user_id": "alice", "name": "Alice", "email": "alice@example.com"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/ludus/users/{user_id}  (delete user)
# ---------------------------------------------------------------------------


def test_delete_user_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.user_rm.return_value = None

    resp = client.delete("/api/ludus/users/alice")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["detail"] == "User deleted"
    mock_ludus.user_rm.assert_called_once_with("alice")


def test_delete_user_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.user_rm.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.delete("/api/ludus/users/ghost")
    assert resp.status_code == 404


def test_delete_user_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.user_rm.side_effect = LudusError("internal", status_code=500)

    resp = client.delete("/api/ludus/users/alice")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_delete_user_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.delete("/api/ludus/users/alice")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/ludus/users/{user_id}/wireguard  (download WireGuard config)
# ---------------------------------------------------------------------------


def test_get_user_wireguard_success(client: TestClient, mock_ludus: MagicMock) -> None:
    mock_ludus.user_wireguard.return_value = "[Interface]\nPrivateKey=abc\n"

    resp = client.get("/api/ludus/users/alice/wireguard")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == "attachment; filename=alice.conf"
    assert "[Interface]" in resp.text
    mock_ludus.user_wireguard.assert_called_once_with("alice")


def test_get_user_wireguard_not_found_returns_404(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.user_wireguard.side_effect = LudusNotFound("not found", status_code=404)

    resp = client.get("/api/ludus/users/ghost/wireguard")
    assert resp.status_code == 404


def test_get_user_wireguard_ludus_error_returns_502(
    client: TestClient, mock_ludus: MagicMock
) -> None:
    mock_ludus.user_wireguard.side_effect = LudusError("internal", status_code=500)

    resp = client.get("/api/ludus/users/alice/wireguard")
    assert resp.status_code == 502
    assert "Ludus error" in resp.json()["detail"]


def test_get_user_wireguard_without_auth_returns_401(anon_client: TestClient) -> None:
    resp = anon_client.get("/api/ludus/users/alice/wireguard")
    assert resp.status_code == 401
