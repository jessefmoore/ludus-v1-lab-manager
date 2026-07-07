"""Unit tests for `app.services.ludus.LudusClient` against the Ludus v1 contract.

Ludus v1 (1.11.x) serves bare routes (no /api/v2 prefix), addresses ranges by
``?userID=``, shares ranges via POST /range/access, and lacks a number of
endpoints that newer Ludus versions added. These tests pin that contract.

Uses pytest-httpx's ``httpx_mock`` fixture to intercept outbound requests.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pytest_httpx import HTTPXMock

from app.services.exceptions import (
    LudusAuthError,
    LudusError,
    LudusNotFound,
    LudusNotSupported,
    LudusUserExists,
)
from app.services.ludus import API_BASE, LudusClient

BASE_URL = "https://ludus.test:8080"
API_KEY = "super-secret-ludus-key-do-not-log-me"


@pytest.fixture
def client() -> Iterator[LudusClient]:
    c = LudusClient(url=BASE_URL, api_key=API_KEY, verify_tls=False)
    try:
        yield c
    finally:
        c.close()


def _url(path: str) -> str:
    return f"{BASE_URL}{API_BASE}{path}"


# ---------------------------------------------------------------------------
# v1 uses bare routes (no /api/v2 prefix)
# ---------------------------------------------------------------------------


def test_api_base_has_no_version_prefix() -> None:
    assert API_BASE == ""


def test_routes_are_bare(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/user/all"), json=[])
    client.user_list()
    sent = httpx_mock.get_request()
    assert sent is not None
    assert sent.url.path == "/user/all"  # not /api/v2/user/all
    assert sent.headers["X-API-KEY"] == API_KEY


# ---------------------------------------------------------------------------
# user management
# ---------------------------------------------------------------------------


def test_user_add_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url=_url("/user"),
        status_code=201,
        json={"userID": "alice", "name": "Alice", "apiKey": "alice-key", "isAdmin": False},
    )
    result = client.user_add("alice", "Alice", "alice@example.com")
    assert result["userID"] == "alice"
    assert result["apiKey"] == "alice-key"

    sent = httpx_mock.get_request()
    assert sent is not None
    body = sent.read().decode()
    assert '"userID": "alice"' in body or '"userID":"alice"' in body
    assert "alice@example.com" in body


def test_user_add_conflict_raises_exists(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST", url=_url("/user"), status_code=409,
        json={"error": "User with that ID already exists"},
    )
    with pytest.raises(LudusUserExists):
        client.user_add("alice", "Alice", "alice@example.com")


def test_user_add_400_already_exists_raises_exists(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="POST", url=_url("/user"), status_code=400,
        json={"error": "User with that name already exists"},
    )
    with pytest.raises(LudusUserExists):
        client.user_add("alice", "Alice", "alice@example.com")


def test_user_rm_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="DELETE", url=_url("/user/alice"), status_code=200, json={})
    client.user_rm("alice")
    assert httpx_mock.get_request() is not None


def test_user_writes_use_admin_url(httpx_mock: HTTPXMock) -> None:
    # On Ludus v1, user create/delete must hit the admin API (:8081), while
    # everything else uses the primary URL (:8080).
    admin = "https://ludus.test:8081"
    c = LudusClient(url=BASE_URL, api_key=API_KEY, verify_tls=False, admin_url=admin)
    try:
        httpx_mock.add_response(
            method="POST", url=f"{admin}/user", status_code=201,
            json={"userID": "bob", "isAdmin": False, "name": "Bob"},
        )
        httpx_mock.add_response(method="DELETE", url=f"{admin}/user/bob", json={})
        httpx_mock.add_response(method="GET", url=f"{BASE_URL}/user/all", json=[])

        c.user_add("bob", "Bob", "bob@example.com")
        c.user_rm("bob")
        c.user_list()  # reads still go to the primary :8080 URL
    finally:
        c.close()

    reqs = httpx_mock.get_requests()
    assert str(reqs[0].url) == f"{admin}/user"          # add -> admin
    assert str(reqs[1].url) == f"{admin}/user/bob"      # rm  -> admin
    assert reqs[2].url.host == "ludus.test" and reqs[2].url.port == 8080  # list -> primary


def test_user_list_success(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/user/all"),
        json=[{"userID": "JM", "isAdmin": True}, {"userID": "BOB", "isAdmin": False}],
    )
    users = client.user_list()
    assert [u["userID"] for u in users] == ["JM", "BOB"]


def test_user_wireguard_json_wrapped(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/user/wireguard?userID=JM"),
        json={"result": {"wireGuardConfig": "[Interface]\nPrivateKey = x\n"}},
    )
    cfg = client.user_wireguard("JM")
    assert cfg.startswith("[Interface]")
    sent = httpx_mock.get_request()
    assert sent.url.params["userID"] == "JM"


def test_user_wireguard_raw_text_fallback(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/user/wireguard?userID=JM"),
        text="[Interface]\nPrivateKey = y\n",
        headers={"content-type": "text/plain"},
    )
    assert client.user_wireguard("JM").startswith("[Interface]")


# ---------------------------------------------------------------------------
# range sharing via /range/access (v1 replacement for /ranges/assign)
# ---------------------------------------------------------------------------


def test_range_access_grant_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/range/access"), json={"result": "ok"})
    client.range_access_grant("STU1", "LEAD")
    sent = httpx_mock.get_request()
    assert sent.url.path == "/range/access"
    body = sent.read().decode()
    assert '"action": "grant"' in body or '"action":"grant"' in body
    assert "STU1" in body and "LEAD" in body
    assert '"sourceUserID"' in body and '"targetUserID"' in body


def test_range_access_revoke_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/range/access"), json={"result": "ok"})
    client.range_access_revoke("STU1", "LEAD")
    body = httpx_mock.get_request().read().decode()
    assert '"action": "revoke"' in body or '"action":"revoke"' in body


def test_range_access_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/access"),
        json=[{"targetUserID": "LEAD", "sourceUserIDs": ["STU1", "STU2"]}],
    )
    accesses = client.range_access_list()
    assert accesses[0]["targetUserID"] == "LEAD"


# ---------------------------------------------------------------------------
# range deploy / config / lifecycle (keyed by ?userID=)
# ---------------------------------------------------------------------------


def test_range_deploy_two_steps(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=_url("/range/config?userID=JM"), json={})
    httpx_mock.add_response(method="POST", url=_url("/range/deploy?userID=JM"), json={})
    client.range_deploy("JM", "ludus:\n  - vm_name: x\n")
    reqs = httpx_mock.get_requests()
    assert reqs[0].method == "PUT" and reqs[0].url.path == "/range/config"
    assert reqs[1].method == "POST" and reqs[1].url.path == "/range/deploy"
    assert reqs[0].url.params["userID"] == "JM"


def test_range_deploy_existing(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/range/deploy?userID=JM"), json={})
    client.range_deploy_existing(user_id="JM")
    assert httpx_mock.get_request().url.params["userID"] == "JM"


def test_range_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/all"),
        json=[{"userID": "JM", "rangeNumber": 2, "rangeState": "SUCCESS"}],
    )
    ranges = client.range_list()
    assert ranges[0]["userID"] == "JM"
    assert ranges[0]["rangeNumber"] == 2


def test_range_get_config_result_envelope(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/config?userID=JM"),
        json={"result": "ludus:\n  - vm_name: dc\n"},
    )
    cfg = client.range_get_config(user_id="JM")
    assert cfg.startswith("ludus:")


def test_range_get_vms_returns_single_object(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range?userID=JM"),
        json={
            "userID": "JM", "rangeNumber": 2, "numberOfVMs": 1,
            "VMs": [{"ID": 3969, "proxmoxID": 114, "name": "dc", "poweredOn": True, "ip": "10.2.10.5"}],
        },
    )
    detail = client.range_get_vms(user_id="JM")
    assert isinstance(detail, dict)
    assert detail["userID"] == "JM"
    assert detail["VMs"][0]["proxmoxID"] == 114


def test_range_destroy_userid_and_force(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="DELETE", url=_url("/range?userID=JM&force=true"), json={})
    client.range_destroy(user_id="JM", force=True)
    sent = httpx_mock.get_request()
    assert sent.url.params["userID"] == "JM"
    assert sent.url.params["force"] == "true"


def test_range_abort(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/range/abort?userID=JM"), json={"result": "ok"})
    client.range_abort(user_id="JM")
    assert httpx_mock.get_request().url.params["userID"] == "JM"


def test_range_tags(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/range/tags"), json={"tags": ["dc", "kali"]})
    assert client.range_tags() == ["dc", "kali"]


def test_range_config_example(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/config/example"), json={"result": "ludus: []\n"}
    )
    assert client.range_config_example().startswith("ludus:")


# ---------------------------------------------------------------------------
# power management
# ---------------------------------------------------------------------------


def test_range_power_on(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=_url("/range/poweron?userID=JM"), json={})
    client.range_power_on("JM", machines=["dc"])
    sent = httpx_mock.get_request()
    assert sent.url.params["userID"] == "JM"
    assert '"dc"' in sent.read().decode()


def test_range_power_off_default_all(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=_url("/range/poweroff?userID=JM"), json={})
    client.range_power_off("JM")
    assert '"all"' in httpx_mock.get_request().read().decode()


# ---------------------------------------------------------------------------
# snapshots (v1 wraps list in {"snapshots": [...]})
# ---------------------------------------------------------------------------


def test_snapshot_list_unwraps_snapshots(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/snapshots/list?userID=JM"),
        json={"errors": None, "snapshots": [{"name": "before", "vmid": 114}]},
    )
    snaps = client.snapshot_list(user_id="JM")
    assert isinstance(snaps, list)
    assert snaps[0]["name"] == "before"


def test_snapshot_list_empty_when_no_snapshots_key(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/snapshots/list?userID=JM"), json={"errors": None}
    )
    assert client.snapshot_list(user_id="JM") == []


def test_snapshot_create_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/snapshots/create?userID=JM"), json={"result": "ok"})
    client.snapshot_create("snap1", user_id="JM", description="d", include_ram=False, vmids=[114])
    body = httpx_mock.get_request().read().decode()
    assert '"name": "snap1"' in body or '"name":"snap1"' in body
    assert '"includeRAM": false' in body or '"includeRAM":false' in body
    assert "114" in body


def test_snapshot_revert_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/snapshots/rollback?userID=JM"), json={})
    client.snapshot_revert("snap1", user_id="JM")
    sent = httpx_mock.get_request()
    assert sent.url.path == "/snapshots/rollback"
    assert "snap1" in sent.read().decode()


def test_snapshot_delete_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/snapshots/remove?userID=JM"), json={})
    client.snapshot_delete("snap1", user_id="JM")
    assert httpx_mock.get_request().url.path == "/snapshots/remove"


# ---------------------------------------------------------------------------
# testing (keyed by ?userID=, no range_id)
# ---------------------------------------------------------------------------


def test_testing_start(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=_url("/testing/start?userID=JM"), json={"result": "ok"})
    client.testing_start(user_id="JM")
    assert httpx_mock.get_request().url.params["userID"] == "JM"


def test_testing_stop_force(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=_url("/testing/stop?userID=JM"), json={"result": "ok"})
    client.testing_stop(user_id="JM", force=True)
    assert '"force":true' in httpx_mock.get_request().read().decode()


def test_testing_allow_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/testing/allow?userID=JM"), json={})
    client.testing_allow(user_id="JM", domains=["example.com"], ips=["1.2.3.4"])
    body = httpx_mock.get_request().read().decode()
    assert "example.com" in body and "1.2.3.4" in body


def test_testing_deny_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/testing/deny?userID=JM"), json={})
    client.testing_deny(user_id="JM", domains=["evil.com"])
    assert "evil.com" in httpx_mock.get_request().read().decode()


def test_testing_update(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/testing/update?userID=JM"), json={})
    client.testing_update("dc", user_id="JM")
    assert "dc" in httpx_mock.get_request().read().decode()


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------


def test_template_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/templates"), json=[{"name": "win2019"}])
    assert client.template_list()[0]["name"] == "win2019"


def test_template_build_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/templates"), json={})
    client.template_build(["win2019"], parallel=2)
    body = httpx_mock.get_request().read().decode()
    assert "win2019" in body and "2" in body


def test_template_abort(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/templates/abort"), json={})
    client.template_abort()
    assert httpx_mock.get_request().url.path == "/templates/abort"


def test_template_status(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/templates/status"), json=[{"template": "x"}])
    assert client.template_status()[0]["template"] == "x"


def test_template_logs(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/templates/logs"), json={"result": "log text"})
    assert client.template_logs() == "log text"


def test_template_delete(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="DELETE", url=_url("/template/win2019"), json={})
    client.template_delete("win2019")
    assert httpx_mock.get_request().url.path == "/template/win2019"


# ---------------------------------------------------------------------------
# range detail (read-only)
# ---------------------------------------------------------------------------


def test_range_logs(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/range/logs?userID=JM"), json={"result": "..."})
    assert client.range_logs(user_id="JM")["result"] == "..."


def test_range_etchosts(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/etchosts?userID=JM"), json={"result": "10.2.10.5 dc"}
    )
    assert "dc" in client.range_etchosts(user_id="JM")


def test_range_sshconfig(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/range/sshconfig"), json={"result": "Host dc"})
    assert "Host dc" in client.range_sshconfig()


def test_range_rdpconfigs_bytes(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/rdpconfigs?userID=JM"), content=b"PK\x03\x04zip",
    )
    assert client.range_rdpconfigs(user_id="JM") == b"PK\x03\x04zip"


def test_range_ansibleinventory(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/ansibleinventory?userID=JM"), json={"result": "all:\n"}
    )
    assert client.range_ansibleinventory(user_id="JM").startswith("all:")


# ---------------------------------------------------------------------------
# ansible
# ---------------------------------------------------------------------------


def test_ansible_list(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/ansible?userID=JM"), json=[{"name": "role1"}])
    assert client.ansible_list(user_id="JM")[0]["name"] == "role1"


def test_ansible_role_body(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/ansible/role"), json={"result": "ok"})
    client.ansible_role("badsectorlabs.ludus_bloodhound_ce", "install", global_=True)
    body = httpx_mock.get_request().read().decode()
    assert '"action": "install"' in body or '"action":"install"' in body
    assert '"global": true' in body or '"global":true' in body


def test_ansible_collection(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="POST", url=_url("/ansible/collection"), json={"result": "ok"})
    client.ansible_collection("community.general", version="1.0.0")
    assert "community.general" in httpx_mock.get_request().read().decode()


def test_ansible_role_from_tar(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="PUT", url=_url("/ansible/role/fromtar"), json={"result": "ok"})
    client.ansible_role_from_tar(b"tardata", "role.tar.gz", force=True)
    assert httpx_mock.get_request().url.path == "/ansible/role/fromtar"


def test_ansible_scope_roles_global_installs_each(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(method="POST", url=_url("/ansible/role"), json={"result": "ok"})
    httpx_mock.add_response(method="POST", url=_url("/ansible/role"), json={"result": "ok"})
    client.ansible_scope_roles_global(["role1", "role2"])
    reqs = httpx_mock.get_requests()
    assert len(reqs) == 2
    for r in reqs:
        assert '"global": true' in r.read().decode() or '"global":true' in r.read().decode()


def test_ansible_scope_roles_global_propagates_failure(
    client: LudusClient, httpx_mock: HTTPXMock
) -> None:
    # A failing role propagates so provisioning can record it as non-fatal.
    httpx_mock.add_response(method="POST", url=_url("/ansible/role"), status_code=500, json={"error": "x"})
    with pytest.raises(LudusError):
        client.ansible_scope_roles_global(["role1"])


# ---------------------------------------------------------------------------
# error mapping
# ---------------------------------------------------------------------------


def test_auth_error_401(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/user/all"), status_code=401, json={"error": "no key"})
    with pytest.raises(LudusAuthError):
        client.user_list()


def test_not_found_404(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET", url=_url("/range/config?userID=NOPE"), status_code=404, json={"error": "no range"}
    )
    with pytest.raises(LudusNotFound):
        client.range_get_config(user_id="NOPE")


def test_generic_error_500(client: LudusClient, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(method="GET", url=_url("/range/all"), status_code=500, json={"error": "boom"})
    with pytest.raises(LudusError):
        client.range_list()


# ---------------------------------------------------------------------------
# operations NOT supported on Ludus v1 -> LudusNotSupported (no HTTP call)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.range_assign("u", "r"),
        lambda c: c.range_revoke("u", "r"),
        lambda c: c.range_users("r"),
        lambda c: c.range_create("name", 1),
        lambda c: c.ranges_accessible(),
        lambda c: c.range_delete_vms(1),
        lambda c: c.vm_destroy(1),
        lambda c: c.range_logs_history(),
        lambda c: c.range_log_entry(1),
        lambda c: c.whoami(),
        lambda c: c.group_create("g"),
        lambda c: c.group_list(),
        lambda c: c.group_delete("g"),
        lambda c: c.group_users("g"),
        lambda c: c.group_add_users("g", ["u"]),
        lambda c: c.group_remove_users("g", ["u"]),
        lambda c: c.group_ranges("g"),
        lambda c: c.group_add_ranges("g", [1]),
        lambda c: c.group_remove_ranges("g", [1]),
        lambda c: c.ansible_subscription_roles(),
        lambda c: c.ansible_install_subscription_roles(["r"]),
        lambda c: c.ansible_role_vars(["r"]),
        lambda c: c.ansible_role_scope(["r"], global_=True),
    ],
)
def test_unsupported_operations_raise(client: LudusClient, call) -> None:
    with pytest.raises(LudusNotSupported):
        call(client)
