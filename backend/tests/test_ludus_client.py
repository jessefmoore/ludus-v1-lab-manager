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


def test_user_wireguard_returns_text_from_json(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
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


def test_context_manager_closes_client() -> None:
    with LudusClient(url=BASE_URL, api_key=API_KEY) as c:
        assert isinstance(c, LudusClient)
    # The inner httpx client should now be closed — issuing a request
    # should fail.
    with pytest.raises(RuntimeError):
        c._client.get("/anything")
