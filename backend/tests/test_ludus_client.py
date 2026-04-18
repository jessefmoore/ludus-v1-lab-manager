"""Unit tests for `app.services.ludus.LudusClient`.

Uses pytest-httpx's `httpx_mock` fixture to intercept outbound HTTP
requests made by the internal `httpx.Client`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.services.exceptions import (
    LudusAuthError,
    LudusError,
    LudusNotFound,
    LudusTimeout,
    LudusUserExists,
)
from app.services.ludus import API_BASE, LudusClient

BASE_URL = "https://ludus.test:8080"
API_KEY = "super-secret-ludus-key-do-not-log-me"


@pytest.fixture
def client() -> Iterator[LudusClient]:
    """A fresh LudusClient pointing at BASE_URL, closed after the test."""
    c = LudusClient(url=BASE_URL, api_key=API_KEY, verify_tls=False)
    try:
        yield c
    finally:
        c.close()


def _url(path: str) -> str:
    return f"{BASE_URL}{API_BASE}{path}"


# ---------------------------------------------------------------------------
# user_add
# ---------------------------------------------------------------------------


def test_user_add_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/user"),
        status_code=201,
        json={
            "userID": "alice",
            "name": "Alice",
            "apiKey": "alice-key",
            "isAdmin": False,
        },
    )

    result = client.user_add("alice", "Alice", "alice@example.com")

    assert result["userID"] == "alice"
    assert result["apiKey"] == "alice-key"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert sent.headers["X-API-KEY"] == API_KEY


def test_user_add_conflict_raises_exists(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/user"),
        status_code=409,
        json={"error": "User with that ID already exists"},
    )

    with pytest.raises(LudusUserExists) as exc:
        client.user_add("alice", "Alice", "alice@example.com")
    assert exc.value.status_code == 409


def test_user_add_400_already_exists_raises_exists(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    # Real Ludus sometimes returns 400 for duplicate userID.
    httpx_mock.add_response(
        method="POST",
        url=_url("/user"),
        status_code=400,
        json={"error": "User with that ID already exists"},
    )
    with pytest.raises(LudusUserExists):
        client.user_add("alice", "Alice", "alice@example.com")


def test_user_add_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/user"),
        status_code=401,
        json={"error": "invalid api key"},
    )

    with pytest.raises(LudusAuthError) as exc:
        client.user_add("alice", "Alice", "alice@example.com")
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# user_rm
# ---------------------------------------------------------------------------


def test_user_rm_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/user/alice"),
        status_code=204,
    )

    result = client.user_rm("alice")
    assert result is None


def test_user_rm_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/user/ghost"),
        status_code=404,
        json={"error": "user not found"},
    )
    with pytest.raises(LudusNotFound):
        client.user_rm("ghost")


# ---------------------------------------------------------------------------
# range_assign
# ---------------------------------------------------------------------------


def test_range_assign_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ranges/assign/alice/RZ1"),
        status_code=200,
        json={"result": "assigned"},
    )

    result = client.range_assign("alice", "RZ1")
    assert result is None


# ---------------------------------------------------------------------------
# user_wireguard
# ---------------------------------------------------------------------------


WG_CONFIG = (
    "[Interface]\n"
    "PrivateKey = abc123\n"
    "Address = 198.51.100.5/32\n"
    "\n"
    "[Peer]\n"
    "PublicKey = def456\n"
    "Endpoint = 198.51.100.1:51820\n"
    "AllowedIPs = 10.5.0.0/16\n"
    "PersistentKeepalive = 25\n"
)


def test_user_wireguard_returns_text_from_json(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/user/wireguard')}?userID=alice",
        status_code=200,
        json={"result": {"wireGuardConfig": WG_CONFIG}},
    )

    config = client.user_wireguard("alice")
    assert isinstance(config, str)
    assert config == WG_CONFIG
    assert "[Interface]" in config


def test_user_wireguard_returns_text_from_raw_body(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/user/wireguard')}?userID=alice",
        status_code=200,
        text=WG_CONFIG,
        headers={"content-type": "text/plain"},
    )

    config = client.user_wireguard("alice")
    assert config == WG_CONFIG


# ---------------------------------------------------------------------------
# snapshot_revert
# ---------------------------------------------------------------------------


def test_snapshot_revert_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/rollback')}?userID=alice",
        status_code=200,
        json={"result": "rollback started"},
    )

    assert client.snapshot_revert("alice", "ctf-initial") is None

    sent = httpx_mock.get_request()
    assert sent is not None
    # Body includes the snapshot name.
    assert b"ctf-initial" in sent.content


def test_snapshot_revert_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/rollback')}?userID=alice",
        status_code=404,
        json={"error": "snapshot not found"},
    )
    with pytest.raises(LudusNotFound):
        client.snapshot_revert("alice", "nope")


# ---------------------------------------------------------------------------
# range_deploy
# ---------------------------------------------------------------------------


def test_range_deploy_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/config')}?userID=alice",
        status_code=200,
        json={"result": "config uploaded"},
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/range/deploy')}?userID=alice",
        status_code=200,
        json={"result": "Range deploy started"},
    )

    result = client.range_deploy("alice", "ludus:\n  - vm_name: test\n")
    assert result is None

    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    # First request is multipart upload — content type should be multipart.
    assert requests[0].method == "PUT"
    assert "multipart/form-data" in requests[0].headers["content-type"]
    # Body should contain the YAML text.
    assert b"vm_name: test" in requests[0].content
    # Second request is the deploy trigger.
    assert requests[1].method == "POST"


def test_range_deploy_config_rejected(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    # If config upload returns 400 we should get LudusError and never
    # fire the second request.
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/config')}?userID=alice",
        status_code=400,
        json={"error": "Configuration error: bad yaml"},
    )
    with pytest.raises(LudusError) as exc:
        client.range_deploy("alice", "!!not yaml")
    assert exc.value.status_code == 400

    # Only one request should have been sent (config step).
    assert len(httpx_mock.get_requests()) == 1


# ---------------------------------------------------------------------------
# range_list
# ---------------------------------------------------------------------------


def test_range_list_returns_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/all"),
        status_code=200,
        json=[
            {"rangeID": "RZ", "rangeNumber": 1},
            {"rangeID": "RZ2", "rangeNumber": 2},
        ],
    )
    ranges = client.range_list()
    assert isinstance(ranges, list)
    assert len(ranges) == 2
    assert ranges[0]["rangeID"] == "RZ"


def test_range_list_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    # Some Ludus versions return a bare object when there is only one range.
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/all"),
        status_code=200,
        json={"rangeID": "RZ", "rangeNumber": 1},
    )
    ranges = client.range_list()
    assert ranges == [{"rangeID": "RZ", "rangeNumber": 1}]


# ---------------------------------------------------------------------------
# range_get_config
# ---------------------------------------------------------------------------


RANGE_CONFIG_YAML = """\
ludus:
  - vm_name: "{{ range_id }}-web"
    hostname: "{{ range_id }}-web"
    template: debian-12-x64-server-template
    vlan: 10
    ip_last_octet: 10
"""


def test_range_get_config_returns_yaml_from_json(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/config')}?userID=alice",
        status_code=200,
        json={"result": RANGE_CONFIG_YAML},
    )

    config = client.range_get_config(user_id="alice")
    assert isinstance(config, str)
    assert config == RANGE_CONFIG_YAML
    assert "vm_name" in config


def test_range_get_config_by_range_number(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/config')}?rangeNumber=1",
        status_code=200,
        json={"result": RANGE_CONFIG_YAML},
    )

    config = client.range_get_config(range_number=1)
    assert isinstance(config, str)
    assert config == RANGE_CONFIG_YAML


def test_range_get_config_returns_yaml_from_raw_body(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/config')}?userID=alice",
        status_code=200,
        text=RANGE_CONFIG_YAML,
        headers={"content-type": "text/plain"},
    )

    config = client.range_get_config(user_id="alice")
    assert config == RANGE_CONFIG_YAML


def test_range_get_config_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/config')}?rangeNumber=999",
        status_code=404,
        json={"error": "range not found"},
    )
    with pytest.raises(LudusNotFound):
        client.range_get_config(range_number=999)


def test_range_get_config_requires_exactly_one_param(client: LudusClient) -> None:
    with pytest.raises(ValueError, match="Exactly one"):
        client.range_get_config()
    with pytest.raises(ValueError, match="Exactly one"):
        client.range_get_config(user_id="alice", range_number=1)


# ---------------------------------------------------------------------------
# Error translation: timeout, 5xx
# ---------------------------------------------------------------------------


def test_timeout_raises_ludus_timeout() -> None:
    def _raise_timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("boom")

    transport = httpx.MockTransport(_raise_timeout)
    inner = httpx.Client(
        base_url=BASE_URL,
        transport=transport,
        headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
    )
    client = LudusClient(url=BASE_URL, api_key=API_KEY, client=inner)
    try:
        with pytest.raises(LudusTimeout):
            client.user_rm("alice")
    finally:
        client.close()


def test_generic_5xx_raises_ludus_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/all"),
        status_code=503,
        json={"error": "service unavailable"},
    )
    with pytest.raises(LudusError) as exc:
        client.range_list()
    assert exc.value.status_code == 503
    assert not isinstance(exc.value, LudusAuthError)
    assert not isinstance(exc.value, LudusNotFound)
    assert not isinstance(exc.value, LudusUserExists)


# ---------------------------------------------------------------------------
# Logging safety
# ---------------------------------------------------------------------------


def test_api_key_never_logged(
    client: LudusClient,
    httpx_mock: HTTPXMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/user"),
        status_code=201,
        json={"userID": "alice", "apiKey": "returned-apikey"},
    )
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/rollback')}?userID=alice",
        status_code=500,
        json={"error": "boom"},
    )

    with caplog.at_level(logging.DEBUG, logger="app.services.ludus"):
        client.user_add("alice", "Alice", "alice@example.com")
        with pytest.raises(LudusError):
            client.snapshot_revert("alice", "ctf-initial")

    # Concatenate all log records + the formatted messages.
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert API_KEY not in joined
    # Also ensure api key doesn't leak in exception messages flowing through logs.
    assert "super-secret" not in joined


# ---------------------------------------------------------------------------
# Context manager support
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# user_list
# ---------------------------------------------------------------------------


def test_user_list_returns_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/user/all"),
        status_code=200,
        json=[
            {"userID": "alice", "name": "Alice"},
            {"userID": "bob", "name": "Bob"},
        ],
    )
    users = client.user_list()
    assert isinstance(users, list)
    assert len(users) == 2
    assert users[0]["userID"] == "alice"


def test_user_list_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/user/all"),
        status_code=200,
        json={"userID": "alice", "name": "Alice"},
    )
    users = client.user_list()
    assert users == [{"userID": "alice", "name": "Alice"}]


# ---------------------------------------------------------------------------
# range_destroy
# ---------------------------------------------------------------------------


def test_range_destroy_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{_url('/range')}?rangeNumber=1",
        status_code=200,
        json={"result": "range destroyed"},
    )

    result = client.range_destroy(1)
    assert result is None


def test_range_destroy_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{_url('/range')}?rangeNumber=999",
        status_code=404,
        json={"error": "range not found"},
    )
    with pytest.raises(LudusNotFound):
        client.range_destroy(999)


# ---------------------------------------------------------------------------
# range_deploy_existing
# ---------------------------------------------------------------------------


def test_range_deploy_existing_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/range/deploy')}?rangeNumber=1",
        status_code=200,
        json={"result": "deploy started"},
    )

    result = client.range_deploy_existing(range_number=1)
    assert result is None


def test_range_deploy_existing_requires_one_param(client: LudusClient) -> None:
    with pytest.raises(ValueError, match="Exactly one"):
        client.range_deploy_existing()
    with pytest.raises(ValueError, match="Exactly one"):
        client.range_deploy_existing(user_id="alice", range_number=1)


# ---------------------------------------------------------------------------
# Context manager support
# ---------------------------------------------------------------------------


def test_context_manager_closes_client() -> None:
    with LudusClient(url=BASE_URL, api_key=API_KEY) as c:
        assert isinstance(c, LudusClient)
    # The inner httpx client should now be closed — issuing a request
    # should fail.
    with pytest.raises(RuntimeError):
        c._client.get("/anything")


# ---------------------------------------------------------------------------
# range_power_on
# ---------------------------------------------------------------------------


def test_range_power_on_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/poweron')}?userID=alice",
        status_code=200,
        json={"result": "powering on"},
    )

    result = client.range_power_on("alice")
    assert result is None

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"machines"' in sent.content
    assert b'"all"' in sent.content


def test_range_power_on_specific_machines(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/poweron')}?userID=alice",
        status_code=200,
        json={"result": "powering on"},
    )

    client.range_power_on("alice", machines=["web", "db"])

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"web"' in sent.content
    assert b'"db"' in sent.content


def test_range_power_on_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/poweron')}?userID=ghost",
        status_code=404,
        json={"error": "user not found"},
    )
    with pytest.raises(LudusNotFound):
        client.range_power_on("ghost")


def test_range_power_on_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/poweron')}?userID=alice",
        status_code=401,
        json={"error": "invalid api key"},
    )
    with pytest.raises(LudusAuthError):
        client.range_power_on("alice")


# ---------------------------------------------------------------------------
# range_power_off
# ---------------------------------------------------------------------------


def test_range_power_off_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/poweroff')}?userID=alice",
        status_code=200,
        json={"result": "powering off"},
    )

    result = client.range_power_off("alice")
    assert result is None


def test_range_power_off_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/range/poweroff')}?userID=ghost",
        status_code=404,
        json={"error": "user not found"},
    )
    with pytest.raises(LudusNotFound):
        client.range_power_off("ghost")


# ---------------------------------------------------------------------------
# snapshot_revert (updated — vmids parameter)
# ---------------------------------------------------------------------------


def test_snapshot_revert_with_vmids(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/rollback')}?userID=alice",
        status_code=200,
        json={"result": "rollback started"},
    )

    client.snapshot_revert("alice", "ctf-initial", vmids=[100, 101])

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"vmIDs"' in sent.content
    assert b"100" in sent.content


# ---------------------------------------------------------------------------
# snapshot_list
# ---------------------------------------------------------------------------


def test_snapshot_list_returns_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/snapshots/list')}?userID=alice",
        status_code=200,
        json=[
            {"name": "ctf-initial", "description": "Clean state"},
            {"name": "checkpoint-1", "description": "After setup"},
        ],
    )

    snapshots = client.snapshot_list(user_id="alice")
    assert isinstance(snapshots, list)
    assert len(snapshots) == 2
    assert snapshots[0]["name"] == "ctf-initial"


def test_snapshot_list_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/snapshots/list')}?userID=alice",
        status_code=200,
        json={"name": "ctf-initial"},
    )

    snapshots = client.snapshot_list(user_id="alice")
    assert snapshots == [{"name": "ctf-initial"}]


def test_snapshot_list_by_range_number(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/snapshots/list')}?rangeNumber=1",
        status_code=200,
        json=[{"name": "snap1"}],
    )

    snapshots = client.snapshot_list(range_number=1)
    assert len(snapshots) == 1


def test_snapshot_list_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/snapshots/list')}?userID=ghost",
        status_code=404,
        json={"error": "user not found"},
    )
    with pytest.raises(LudusNotFound):
        client.snapshot_list(user_id="ghost")


# ---------------------------------------------------------------------------
# snapshot_create
# ---------------------------------------------------------------------------


def test_snapshot_create_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/create')}?userID=alice",
        status_code=200,
        json={"result": "snapshot creation started"},
    )

    result = client.snapshot_create("alice", "my-snap", description="test snapshot")
    assert result is None

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"name"' in sent.content
    assert b'"my-snap"' in sent.content
    assert b'"includeRAM"' in sent.content


def test_snapshot_create_with_vmids(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/create')}?userID=alice",
        status_code=200,
        json={"result": "snapshot creation started"},
    )

    client.snapshot_create("alice", "my-snap", vmids=[100, 101], include_ram=True)

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"vmIDs"' in sent.content
    assert b"100" in sent.content


def test_snapshot_create_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/create')}?userID=alice",
        status_code=403,
        json={"error": "forbidden"},
    )
    with pytest.raises(LudusAuthError):
        client.snapshot_create("alice", "snap1")


# ---------------------------------------------------------------------------
# snapshot_delete
# ---------------------------------------------------------------------------


def test_snapshot_delete_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/remove')}?userID=alice",
        status_code=200,
        json={"result": "snapshot removed"},
    )

    result = client.snapshot_delete("alice", "old-snap")
    assert result is None

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"old-snap"' in sent.content


def test_snapshot_delete_with_vmids(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/remove')}?userID=alice",
        status_code=200,
        json={"result": "snapshot removed"},
    )

    client.snapshot_delete("alice", "old-snap", vmids=[100])

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"vmIDs"' in sent.content


def test_snapshot_delete_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/snapshots/remove')}?userID=alice",
        status_code=404,
        json={"error": "snapshot not found"},
    )
    with pytest.raises(LudusNotFound):
        client.snapshot_delete("alice", "nope")


# ---------------------------------------------------------------------------
# template_list
# ---------------------------------------------------------------------------


def test_template_list_returns_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/templates"),
        status_code=200,
        json=[
            {"name": "debian-12-x64-server-template", "os": "Debian 12"},
            {"name": "win11-22h2-x64-enterprise-template", "os": "Windows 11"},
        ],
    )

    templates = client.template_list()
    assert isinstance(templates, list)
    assert len(templates) == 2
    assert templates[0]["name"] == "debian-12-x64-server-template"


def test_template_list_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/templates"),
        status_code=200,
        json={"name": "debian-12-x64-server-template"},
    )

    templates = client.template_list()
    assert templates == [{"name": "debian-12-x64-server-template"}]


def test_template_list_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/templates"),
        status_code=401,
        json={"error": "invalid api key"},
    )
    with pytest.raises(LudusAuthError):
        client.template_list()


# ---------------------------------------------------------------------------
# template_delete
# ---------------------------------------------------------------------------


def test_template_delete_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/template/debian-12-x64-server-template"),
        status_code=200,
        json={"result": "template deleted"},
    )

    result = client.template_delete("debian-12-x64-server-template")
    assert result is None


def test_template_delete_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/template/nope"),
        status_code=404,
        json={"error": "template not found"},
    )
    with pytest.raises(LudusNotFound):
        client.template_delete("nope")


def test_template_delete_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/template/some-template"),
        status_code=403,
        json={"error": "forbidden"},
    )
    with pytest.raises(LudusAuthError):
        client.template_delete("some-template")


# ---------------------------------------------------------------------------
# range_get_vms
# ---------------------------------------------------------------------------


def test_range_get_vms_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range"),
        status_code=200,
        json=[
            {"vmID": 100, "name": "web", "powerState": "running"},
            {"vmID": 101, "name": "db", "powerState": "stopped"},
        ],
    )
    vms = client.range_get_vms()
    assert isinstance(vms, list)
    assert len(vms) == 2
    assert vms[0]["vmID"] == 100


def test_range_get_vms_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range"),
        status_code=200,
        json={"vmID": 100, "name": "web"},
    )
    vms = client.range_get_vms()
    assert vms == [{"vmID": 100, "name": "web"}]


def test_range_get_vms_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range')}?rangeNumber=1&userID=alice",
        status_code=200,
        json=[{"vmID": 100}],
    )
    vms = client.range_get_vms(range_id=1, user_id="alice")
    assert len(vms) == 1

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# vm_destroy
# ---------------------------------------------------------------------------


def test_vm_destroy_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/vm/100"),
        status_code=200,
        json={"result": "VM destroyed"},
    )
    result = client.vm_destroy(100)
    assert result["result"] == "VM destroyed"


def test_vm_destroy_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/vm/999"),
        status_code=404,
        json={"error": "VM not found"},
    )
    with pytest.raises(LudusNotFound):
        client.vm_destroy(999)


# ---------------------------------------------------------------------------
# range_abort
# ---------------------------------------------------------------------------


def test_range_abort_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/range/abort"),
        status_code=200,
        json={"result": "abort initiated"},
    )
    result = client.range_abort()
    assert result["result"] == "abort initiated"


def test_range_abort_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/range/abort')}?rangeNumber=1&userID=alice",
        status_code=200,
        json={"result": "abort initiated"},
    )
    result = client.range_abort(range_id=1, user_id="alice")
    assert result["result"] == "abort initiated"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# range_delete_vms
# ---------------------------------------------------------------------------


def test_range_delete_vms_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/range/1/vms"),
        status_code=200,
        json={"result": "VMs deleted"},
    )
    result = client.range_delete_vms(1)
    assert result["result"] == "VMs deleted"


def test_range_delete_vms_with_user_id(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{_url('/range/1/vms')}?userID=alice",
        status_code=200,
        json={"result": "VMs deleted"},
    )
    result = client.range_delete_vms(1, user_id="alice")
    assert result["result"] == "VMs deleted"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# range_tags
# ---------------------------------------------------------------------------


def test_range_tags_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/tags"),
        status_code=200,
        json={"tags": ["tag1", "tag2"]},
    )
    tags = client.range_tags()
    assert isinstance(tags, list)
    assert tags == ["tag1", "tag2"]


def test_range_tags_empty(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/tags"),
        status_code=200,
        json={"tags": []},
    )
    tags = client.range_tags()
    assert tags == []


# ---------------------------------------------------------------------------
# range_config_example
# ---------------------------------------------------------------------------


def test_range_config_example_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    example_yaml = "ludus:\n  - vm_name: example\n"
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/config/example"),
        status_code=200,
        json={"result": example_yaml},
    )
    result = client.range_config_example()
    assert isinstance(result, str)
    assert result == example_yaml


def test_range_config_example_raw_text(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    example_yaml = "ludus:\n  - vm_name: example\n"
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/config/example"),
        status_code=200,
        text=example_yaml,
        headers={"content-type": "text/plain"},
    )
    result = client.range_config_example()
    assert result == example_yaml


# ---------------------------------------------------------------------------
# range_logs
# ---------------------------------------------------------------------------


def test_range_logs_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/logs"),
        status_code=200,
        json={"result": "log output", "cursor": "abc123"},
    )
    result = client.range_logs()
    assert result["result"] == "log output"
    assert result["cursor"] == "abc123"


def test_range_logs_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/logs')}?rangeNumber=1&userID=alice&tail=50&cursor=xyz",
        status_code=200,
        json={"result": "log output"},
    )
    result = client.range_logs(range_id=1, user_id="alice", tail=50, cursor="xyz")
    assert result["result"] == "log output"

    sent = httpx_mock.get_request()
    assert sent is not None
    url_str = str(sent.url)
    assert "rangeNumber=1" in url_str
    assert "userID=alice" in url_str
    assert "tail=50" in url_str
    assert "cursor=xyz" in url_str


# ---------------------------------------------------------------------------
# range_logs_history
# ---------------------------------------------------------------------------


def test_range_logs_history_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/logs/history"),
        status_code=200,
        json=[
            {"logID": 1, "timestamp": "2024-01-01T00:00:00Z"},
            {"logID": 2, "timestamp": "2024-01-02T00:00:00Z"},
        ],
    )
    entries = client.range_logs_history()
    assert isinstance(entries, list)
    assert len(entries) == 2
    assert entries[0]["logID"] == 1


def test_range_logs_history_wraps_single_object(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/logs/history"),
        status_code=200,
        json={"logID": 1},
    )
    entries = client.range_logs_history()
    assert entries == [{"logID": 1}]


def test_range_logs_history_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/logs/history')}?rangeNumber=1&userID=alice",
        status_code=200,
        json=[{"logID": 1}],
    )
    entries = client.range_logs_history(range_id=1, user_id="alice")
    assert len(entries) == 1

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# range_log_entry
# ---------------------------------------------------------------------------


def test_range_log_entry_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/logs/history/42"),
        status_code=200,
        json={"logID": 42, "content": "deploy log", "timestamp": "2024-01-01T00:00:00Z"},
    )
    entry = client.range_log_entry(42)
    assert entry["logID"] == 42
    assert entry["content"] == "deploy log"


def test_range_log_entry_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/logs/history/999"),
        status_code=404,
        json={"error": "log entry not found"},
    )
    with pytest.raises(LudusNotFound):
        client.range_log_entry(999)


# ---------------------------------------------------------------------------
# range_etchosts
# ---------------------------------------------------------------------------


def test_range_etchosts_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    hosts_content = "10.5.0.10 web.ludus\n10.5.0.11 db.ludus\n"
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/etchosts"),
        status_code=200,
        json={"result": hosts_content},
    )
    result = client.range_etchosts()
    assert isinstance(result, str)
    assert result == hosts_content


def test_range_etchosts_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/etchosts')}?rangeNumber=1&userID=alice",
        status_code=200,
        json={"result": "10.5.0.10 web.ludus\n"},
    )
    result = client.range_etchosts(range_id=1, user_id="alice")
    assert "web.ludus" in result

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# range_sshconfig
# ---------------------------------------------------------------------------


def test_range_sshconfig_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    ssh_config = "Host web\n  HostName 10.5.0.10\n  User root\n"
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/sshconfig"),
        status_code=200,
        json={"result": ssh_config},
    )
    result = client.range_sshconfig()
    assert isinstance(result, str)
    assert result == ssh_config


def test_range_sshconfig_raw_text(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    ssh_config = "Host web\n  HostName 10.5.0.10\n"
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/sshconfig"),
        status_code=200,
        text=ssh_config,
        headers={"content-type": "text/plain"},
    )
    result = client.range_sshconfig()
    assert result == ssh_config


# ---------------------------------------------------------------------------
# range_rdpconfigs
# ---------------------------------------------------------------------------


def test_range_rdpconfigs_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    zip_data = b"PK\x03\x04fake-zip-content"
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/rdpconfigs"),
        status_code=200,
        content=zip_data,
        headers={"content-type": "application/zip"},
    )
    result = client.range_rdpconfigs()
    assert isinstance(result, bytes)
    assert result == zip_data
    assert result[:2] == b"PK"


def test_range_rdpconfigs_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    zip_data = b"PK\x03\x04fake-zip"
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/rdpconfigs')}?rangeNumber=1&userID=alice",
        status_code=200,
        content=zip_data,
        headers={"content-type": "application/zip"},
    )
    result = client.range_rdpconfigs(range_id=1, user_id="alice")
    assert result == zip_data

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# range_ansibleinventory
# ---------------------------------------------------------------------------


def test_range_ansibleinventory_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    inventory = "all:\n  hosts:\n    web:\n      ansible_host: 10.5.0.10\n"
    httpx_mock.add_response(
        method="GET",
        url=_url("/range/ansibleinventory"),
        status_code=200,
        json={"result": inventory},
    )
    result = client.range_ansibleinventory()
    assert isinstance(result, str)
    assert result == inventory


def test_range_ansibleinventory_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/range/ansibleinventory')}?rangeNumber=1&userID=alice",
        status_code=200,
        json={"result": "all:\n  hosts:\n"},
    )
    result = client.range_ansibleinventory(range_id=1, user_id="alice")
    assert "hosts" in result

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# range_create
# ---------------------------------------------------------------------------


def test_range_create_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ranges/create"),
        status_code=200,
        json={"rangeID": 1, "name": "my-range"},
    )
    result = client.range_create("my-range", 1)
    assert result["rangeID"] == 1
    assert result["name"] == "my-range"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"name"' in sent.content
    assert b'"my-range"' in sent.content
    assert b'"rangeID"' in sent.content


def test_range_create_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ranges/create"),
        status_code=401,
        json={"error": "invalid api key"},
    )
    with pytest.raises(LudusAuthError):
        client.range_create("my-range", 1)


# ---------------------------------------------------------------------------
# range_revoke
# ---------------------------------------------------------------------------


def test_range_revoke_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/ranges/revoke/alice/1"),
        status_code=200,
        json={"result": "access revoked"},
    )
    result = client.range_revoke("alice", 1)
    assert result["result"] == "access revoked"


def test_range_revoke_with_force(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=f"{_url('/ranges/revoke/alice/1')}?force=true",
        status_code=200,
        json={"result": "access revoked"},
    )
    result = client.range_revoke("alice", 1, force=True)
    assert result["result"] == "access revoked"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "force=true" in str(sent.url)


def test_range_revoke_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/ranges/revoke/ghost/999"),
        status_code=404,
        json={"error": "not found"},
    )
    with pytest.raises(LudusNotFound):
        client.range_revoke("ghost", 999)


# ---------------------------------------------------------------------------
# range_users
# ---------------------------------------------------------------------------


def test_range_users_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ranges/1/users"),
        status_code=200,
        json=[
            {"userID": "alice", "name": "Alice"},
            {"userID": "bob", "name": "Bob"},
        ],
    )
    users = client.range_users(1)
    assert isinstance(users, list)
    assert len(users) == 2
    assert users[0]["userID"] == "alice"


def test_range_users_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ranges/1/users"),
        status_code=200,
        json={"userID": "alice"},
    )
    users = client.range_users(1)
    assert users == [{"userID": "alice"}]


# ---------------------------------------------------------------------------
# ranges_accessible
# ---------------------------------------------------------------------------


def test_ranges_accessible_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ranges/accessible"),
        status_code=200,
        json=[
            {"rangeID": 1, "name": "lab-1"},
            {"rangeID": 2, "name": "lab-2"},
        ],
    )
    ranges = client.ranges_accessible()
    assert isinstance(ranges, list)
    assert len(ranges) == 2
    assert ranges[0]["rangeID"] == 1


def test_ranges_accessible_wraps_single_object(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ranges/accessible"),
        status_code=200,
        json={"rangeID": 1, "name": "lab-1"},
    )
    ranges = client.ranges_accessible()
    assert ranges == [{"rangeID": 1, "name": "lab-1"}]


# ---------------------------------------------------------------------------
# testing_start
# ---------------------------------------------------------------------------


def test_testing_start_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=_url("/testing/start"),
        status_code=200,
        json={"result": "testing started"},
    )
    result = client.testing_start()
    assert result["result"] == "testing started"


def test_testing_start_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/testing/start')}?rangeNumber=1&userID=alice",
        status_code=200,
        json={"result": "testing started"},
    )
    result = client.testing_start(range_id=1, user_id="alice")
    assert result["result"] == "testing started"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# testing_stop
# ---------------------------------------------------------------------------


def test_testing_stop_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=_url("/testing/stop"),
        status_code=200,
        json={"result": "testing stopped"},
    )
    result = client.testing_stop()
    assert result["result"] == "testing stopped"


def test_testing_stop_with_force(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=f"{_url('/testing/stop')}?rangeNumber=1",
        status_code=200,
        json={"result": "testing stopped"},
    )
    result = client.testing_stop(range_id=1, force=True)
    assert result["result"] == "testing stopped"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"force"' in sent.content


# ---------------------------------------------------------------------------
# testing_allow
# ---------------------------------------------------------------------------


def test_testing_allow_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/testing/allow"),
        status_code=200,
        json={"result": "allow rules added"},
    )
    result = client.testing_allow(domains=["example.com"], ips=["1.2.3.4"])
    assert result["result"] == "allow rules added"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"domains"' in sent.content
    assert b'"example.com"' in sent.content
    assert b'"ips"' in sent.content
    assert b'"1.2.3.4"' in sent.content


def test_testing_allow_with_range_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/testing/allow')}?rangeNumber=1&userID=alice",
        status_code=200,
        json={"result": "allow rules added"},
    )
    result = client.testing_allow(range_id=1, user_id="alice", domains=["test.com"])
    assert result["result"] == "allow rules added"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# testing_deny
# ---------------------------------------------------------------------------


def test_testing_deny_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/testing/deny"),
        status_code=200,
        json={"result": "deny rules added"},
    )
    result = client.testing_deny(domains=["evil.com"], ips=["6.6.6.6"])
    assert result["result"] == "deny rules added"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"domains"' in sent.content
    assert b'"evil.com"' in sent.content
    assert b'"ips"' in sent.content
    assert b'"6.6.6.6"' in sent.content


def test_testing_deny_with_range_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/testing/deny')}?rangeNumber=1&userID=alice",
        status_code=200,
        json={"result": "deny rules added"},
    )
    result = client.testing_deny(range_id=1, user_id="alice", ips=["10.0.0.1"])
    assert result["result"] == "deny rules added"


# ---------------------------------------------------------------------------
# testing_update
# ---------------------------------------------------------------------------


def test_testing_update_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/testing/update"),
        status_code=200,
        json={"result": "testing config updated"},
    )
    result = client.testing_update("my-test-config")
    assert result["result"] == "testing config updated"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"name"' in sent.content
    assert b'"my-test-config"' in sent.content


def test_testing_update_with_params(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=f"{_url('/testing/update')}?rangeNumber=1&userID=alice",
        status_code=200,
        json={"result": "testing config updated"},
    )
    result = client.testing_update("config-name", range_id=1, user_id="alice")
    assert result["result"] == "testing config updated"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "rangeNumber=1" in str(sent.url)
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# group_create
# ---------------------------------------------------------------------------


def test_group_create_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/groups"),
        status_code=200,
        json={"name": "admins", "description": "Admin group"},
    )
    result = client.group_create("admins", description="Admin group")
    assert result["name"] == "admins"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"name"' in sent.content
    assert b'"admins"' in sent.content
    assert b'"description"' in sent.content


def test_group_create_without_description(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/groups"),
        status_code=200,
        json={"name": "students"},
    )
    result = client.group_create("students")
    assert result["name"] == "students"

    sent = httpx_mock.get_request()
    assert sent is not None
    # description key should not be in the body
    assert b'"description"' not in sent.content


# ---------------------------------------------------------------------------
# group_list
# ---------------------------------------------------------------------------


def test_group_list_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/groups"),
        status_code=200,
        json=[
            {"name": "admins", "description": "Admin group"},
            {"name": "students", "description": "Student group"},
        ],
    )
    groups = client.group_list()
    assert isinstance(groups, list)
    assert len(groups) == 2
    assert groups[0]["name"] == "admins"


def test_group_list_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/groups"),
        status_code=200,
        json={"name": "admins"},
    )
    groups = client.group_list()
    assert groups == [{"name": "admins"}]


# ---------------------------------------------------------------------------
# group_delete
# ---------------------------------------------------------------------------


def test_group_delete_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/groups/admins"),
        status_code=204,
    )
    result = client.group_delete("admins")
    assert result is None


def test_group_delete_not_found(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/groups/ghost"),
        status_code=404,
        json={"error": "group not found"},
    )
    with pytest.raises(LudusNotFound):
        client.group_delete("ghost")


# ---------------------------------------------------------------------------
# group_users
# ---------------------------------------------------------------------------


def test_group_users_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/groups/admins/users"),
        status_code=200,
        json=[
            {"userID": "alice", "name": "Alice"},
            {"userID": "bob", "name": "Bob"},
        ],
    )
    users = client.group_users("admins")
    assert isinstance(users, list)
    assert len(users) == 2
    assert users[0]["userID"] == "alice"


def test_group_users_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/groups/admins/users"),
        status_code=200,
        json={"userID": "alice"},
    )
    users = client.group_users("admins")
    assert users == [{"userID": "alice"}]


# ---------------------------------------------------------------------------
# group_add_users
# ---------------------------------------------------------------------------


def test_group_add_users_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/groups/admins/users"),
        status_code=200,
        json={"result": "users added"},
    )
    result = client.group_add_users("admins", ["alice", "bob"])
    assert result["result"] == "users added"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"userIDs"' in sent.content
    assert b'"alice"' in sent.content
    assert b'"bob"' in sent.content


def test_group_add_users_as_managers(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/groups/admins/users"),
        status_code=200,
        json={"result": "managers added"},
    )
    result = client.group_add_users("admins", ["alice"], managers=True)
    assert result["result"] == "managers added"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"managers"' in sent.content


# ---------------------------------------------------------------------------
# group_remove_users
# ---------------------------------------------------------------------------


def test_group_remove_users_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/groups/admins/users"),
        status_code=200,
        json={"result": "users removed"},
    )
    result = client.group_remove_users("admins", ["alice", "bob"])
    assert result["result"] == "users removed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"userIDs"' in sent.content
    assert b'"alice"' in sent.content


# ---------------------------------------------------------------------------
# group_ranges
# ---------------------------------------------------------------------------


def test_group_ranges_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/groups/admins/ranges"),
        status_code=200,
        json=[
            {"rangeID": 1, "name": "lab-1"},
            {"rangeID": 2, "name": "lab-2"},
        ],
    )
    ranges = client.group_ranges("admins")
    assert isinstance(ranges, list)
    assert len(ranges) == 2
    assert ranges[0]["rangeID"] == 1


def test_group_ranges_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/groups/admins/ranges"),
        status_code=200,
        json={"rangeID": 1},
    )
    ranges = client.group_ranges("admins")
    assert ranges == [{"rangeID": 1}]


# ---------------------------------------------------------------------------
# group_add_ranges
# ---------------------------------------------------------------------------


def test_group_add_ranges_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/groups/admins/ranges"),
        status_code=200,
        json={"result": "ranges added"},
    )
    result = client.group_add_ranges("admins", [1, 2])
    assert result["result"] == "ranges added"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"rangeIDs"' in sent.content


# ---------------------------------------------------------------------------
# group_remove_ranges
# ---------------------------------------------------------------------------


def test_group_remove_ranges_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="DELETE",
        url=_url("/groups/admins/ranges"),
        status_code=200,
        json={"result": "ranges removed"},
    )
    result = client.group_remove_ranges("admins", [1, 2])
    assert result["result"] == "ranges removed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"rangeIDs"' in sent.content


# ---------------------------------------------------------------------------
# ansible_subscription_roles
# ---------------------------------------------------------------------------


def test_ansible_subscription_roles_success(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ansible/subscription-roles"),
        status_code=200,
        json=[
            {"name": "role-a", "version": "1.0"},
            {"name": "role-b", "version": "2.0"},
        ],
    )
    roles = client.ansible_subscription_roles()
    assert isinstance(roles, list)
    assert len(roles) == 2
    assert roles[0]["name"] == "role-a"


def test_ansible_subscription_roles_wraps_single_object(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ansible/subscription-roles"),
        status_code=200,
        json={"name": "role-a"},
    )
    roles = client.ansible_subscription_roles()
    assert roles == [{"name": "role-a"}]


# ---------------------------------------------------------------------------
# ansible_install_subscription_roles
# ---------------------------------------------------------------------------


def test_ansible_install_subscription_roles_success(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/subscription-roles"),
        status_code=200,
        json={"result": "roles installed"},
    )
    result = client.ansible_install_subscription_roles(["role-a", "role-b"])
    assert result["result"] == "roles installed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"roles"' in sent.content
    assert b'"role-a"' in sent.content


def test_ansible_install_subscription_roles_with_flags(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/subscription-roles"),
        status_code=200,
        json={"result": "roles installed"},
    )
    result = client.ansible_install_subscription_roles(
        ["role-a"], global_=True, force=True
    )
    assert result["result"] == "roles installed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"global"' in sent.content
    assert b'"force"' in sent.content


# ---------------------------------------------------------------------------
# ansible_role_vars
# ---------------------------------------------------------------------------


def test_ansible_role_vars_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/role/vars"),
        status_code=200,
        json=[
            {"role": "role-a", "vars": {"key": "value"}},
        ],
    )
    result = client.ansible_role_vars(["role-a"])
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["role"] == "role-a"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"roles"' in sent.content
    assert b'"role-a"' in sent.content


def test_ansible_role_vars_wraps_single_object(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/role/vars"),
        status_code=200,
        json={"role": "role-a", "vars": {}},
    )
    result = client.ansible_role_vars(["role-a"])
    assert result == [{"role": "role-a", "vars": {}}]


# ---------------------------------------------------------------------------
# ansible_list
# ---------------------------------------------------------------------------


def test_ansible_list_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ansible"),
        status_code=200,
        json=[
            {"name": "role-a", "type": "role"},
            {"name": "collection-b", "type": "collection"},
        ],
    )
    items = client.ansible_list()
    assert isinstance(items, list)
    assert len(items) == 2
    assert items[0]["name"] == "role-a"


def test_ansible_list_wraps_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=_url("/ansible"),
        status_code=200,
        json={"name": "role-a"},
    )
    items = client.ansible_list()
    assert items == [{"name": "role-a"}]


def test_ansible_list_with_user_id(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url=f"{_url('/ansible')}?userID=alice",
        status_code=200,
        json=[{"name": "role-a"}],
    )
    items = client.ansible_list(user_id="alice")
    assert len(items) == 1

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "userID=alice" in str(sent.url)


# ---------------------------------------------------------------------------
# ansible_role_scope
# ---------------------------------------------------------------------------


def test_ansible_role_scope_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PATCH",
        url=_url("/ansible/role/scope"),
        status_code=200,
        json={"result": "scope changed"},
    )
    result = client.ansible_role_scope(["role-a"])
    assert result["result"] == "scope changed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"roles"' in sent.content
    assert b'"role-a"' in sent.content


def test_ansible_role_scope_with_flags(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PATCH",
        url=_url("/ansible/role/scope"),
        status_code=200,
        json={"result": "scope changed"},
    )
    result = client.ansible_role_scope(["role-a"], global_=True, copy=True)
    assert result["result"] == "scope changed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"global"' in sent.content
    assert b'"copy"' in sent.content


# ---------------------------------------------------------------------------
# ansible_role
# ---------------------------------------------------------------------------


def test_ansible_role_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/role"),
        status_code=200,
        json={"result": "role installed"},
    )
    result = client.ansible_role("geerlingguy.docker", "install")
    assert result["result"] == "role installed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"role"' in sent.content
    assert b'"geerlingguy.docker"' in sent.content
    assert b'"action"' in sent.content
    assert b'"install"' in sent.content


def test_ansible_role_with_options(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/role"),
        status_code=200,
        json={"result": "role installed"},
    )
    result = client.ansible_role(
        "geerlingguy.docker", "install", version="6.1.0", force=True, global_=True
    )
    assert result["result"] == "role installed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"version"' in sent.content
    assert b'"6.1.0"' in sent.content
    assert b'"force"' in sent.content
    assert b'"global"' in sent.content


def test_ansible_role_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/role"),
        status_code=403,
        json={"error": "forbidden"},
    )
    with pytest.raises(LudusAuthError):
        client.ansible_role("some-role", "install")


# ---------------------------------------------------------------------------
# ansible_role_from_tar
# ---------------------------------------------------------------------------


def test_ansible_role_from_tar_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=_url("/ansible/role/fromtar"),
        status_code=200,
        json={"result": "role installed from tar"},
    )
    tar_data = b"\x1f\x8b\x08\x00fake-tar-data"
    result = client.ansible_role_from_tar(tar_data, "my-role.tar.gz")
    assert result["result"] == "role installed from tar"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert "multipart/form-data" in sent.headers["content-type"]
    assert b"my-role.tar.gz" in sent.content


def test_ansible_role_from_tar_with_force(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="PUT",
        url=_url("/ansible/role/fromtar"),
        status_code=200,
        json={"result": "role installed from tar"},
    )
    tar_data = b"\x1f\x8b\x08\x00fake-tar-data"
    result = client.ansible_role_from_tar(tar_data, "my-role.tar.gz", force=True)
    assert result["result"] == "role installed from tar"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b"force" in sent.content


# ---------------------------------------------------------------------------
# ansible_collection
# ---------------------------------------------------------------------------


def test_ansible_collection_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/collection"),
        status_code=200,
        json={"result": "collection installed"},
    )
    result = client.ansible_collection("community.general")
    assert result["result"] == "collection installed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"collection"' in sent.content
    assert b'"community.general"' in sent.content


def test_ansible_collection_with_options(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/collection"),
        status_code=200,
        json={"result": "collection installed"},
    )
    result = client.ansible_collection("community.general", version="7.0.0", force=True)
    assert result["result"] == "collection installed"

    sent = httpx_mock.get_request()
    assert sent is not None
    assert b'"version"' in sent.content
    assert b'"7.0.0"' in sent.content
    assert b'"force"' in sent.content


def test_ansible_collection_auth_error(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/ansible/collection"),
        status_code=401,
        json={"error": "invalid api key"},
    )
    with pytest.raises(LudusAuthError):
        client.ansible_collection("community.general")
