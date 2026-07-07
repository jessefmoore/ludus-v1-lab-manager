"""Single integration point between the platform and a Ludus server.

Every Ludus HTTP call in the backend MUST go through `LudusClient`. This
makes it trivial to swap transports, apply retries/timeouts/logging in one
place, and mock Ludus in tests.

================================================================
TARGET: Ludus v1 (verified against a live 1.11.5+b9fe95c server)
================================================================
Base path:              (none - routes are bare, e.g. /user, /range)
Auth header:            X-API-KEY: <api_key>
Admin impersonation:    append ?userID=<userID> query param (admin key only)

Ludus v1 is SINGLE-RANGE-PER-USER: a user owns exactly one range, addressed
by the user's ID via ``?userID=``. There is no ``rangeID`` string or
``rangeNumber`` request parameter (``rangeNumber`` appears only as a
read-only field in responses). Range sharing is done with the cross-range
access endpoint, not a range-assignment endpoint.

Routes used here (all verified present on 1.11.5):
    POST   /user                                 -> user_add   {userID,name,email,isAdmin}
    DELETE /user/{userID}                         -> user_rm
    GET    /user/all                              -> user_list
    GET    /user/wireguard?userID=<id>            -> user_wireguard  {result:{wireGuardConfig}}
    POST   /range/access                          -> range_access_grant / range_access_revoke
           body: {"action":"grant"|"revoke","sourceUserID","targetUserID","force"}
    GET    /range/access                          -> range_access_list
    PUT    /range/config?userID=<id>              -> range_deploy step 1 (multipart file, force)
    POST   /range/deploy?userID=<id>              -> range_deploy step 2 / range_deploy_existing
    DELETE /range?userID=<id>[&force=true]        -> range_destroy
    GET    /range/all                             -> range_list
    GET    /range?userID=<id>                     -> range_get_vms  (single obj with VMs[])
    GET    /range/config?userID=<id>              -> range_get_config  {result:<yaml>}
    GET    /range/config/example                  -> range_config_example
    POST   /range/abort?userID=<id>               -> range_abort
    PUT    /range/poweron?userID=<id>             -> range_power_on   {machines:[...]}
    PUT    /range/poweroff?userID=<id>            -> range_power_off  {machines:[...]}
    GET    /range/tags                            -> range_tags
    GET    /range/logs?userID=<id>                -> range_logs
    GET    /range/etchosts?userID=<id>            -> range_etchosts
    GET    /range/sshconfig                       -> range_sshconfig
    GET    /range/rdpconfigs?userID=<id>          -> range_rdpconfigs
    GET    /range/ansibleinventory?userID=<id>    -> range_ansibleinventory
    GET    /snapshots/list?userID=<id>            -> snapshot_list  {snapshots:[...]}
    POST   /snapshots/create?userID=<id>          -> snapshot_create
    POST   /snapshots/rollback?userID=<id>        -> snapshot_revert
    POST   /snapshots/remove?userID=<id>          -> snapshot_delete
    PUT    /testing/start?userID=<id>             -> testing_start
    PUT    /testing/stop?userID=<id>              -> testing_stop
    POST   /testing/allow?userID=<id>             -> testing_allow
    POST   /testing/deny?userID=<id>              -> testing_deny
    POST   /testing/update?userID=<id>            -> testing_update
    GET    /templates                             -> template_list
    POST   /templates                             -> template_build
    POST   /templates/abort                       -> template_abort
    GET    /templates/status                      -> template_status
    GET    /templates/logs                        -> template_logs
    DELETE /template/{name}                        -> template_delete
    GET    /ansible?userID=<id>                   -> ansible_list
    POST   /ansible/role                          -> ansible_role  {role,action,global,force,version}
    POST   /ansible/collection                    -> ansible_collection
    PUT    /ansible/role/fromtar                  -> ansible_role_from_tar

NOT AVAILABLE on Ludus v1 (methods raise LudusNotSupported):
    groups (all), /ranges/create, /ranges/accessible, /ranges/assign,
    /ranges/revoke, /whoami, /range/logs/history, /range/{id}/vms,
    /vm/{id}, /templates/logs/history, /ansible/subscription-roles,
    /ansible/role/vars, /ansible/role/scope.
    (Global role scoping on v1 is done via `ansible_role(action="install",
    global_=True)`, exposed here as `ansible_scope_roles_global`.)
================================================================
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.exceptions import (
    LudusAuthError,
    LudusError,
    LudusNotFound,
    LudusNotSupported,
    LudusTimeout,
    LudusUserExists,
)

logger = logging.getLogger(__name__)

# Ludus v1 serves its API at the root - there is NO version prefix.
API_BASE = ""


def _extract_error_detail(response: httpx.Response) -> str:
    """Pull a human-readable error message from a Ludus response."""
    try:
        data = response.json()
    except ValueError:
        return response.text or response.reason_phrase or "Ludus error"
    if isinstance(data, dict):
        for key in ("error", "message", "detail", "result"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return response.text or "Ludus error"


def _raise_for_status(response: httpx.Response, *, on_conflict_user_exists: bool = False) -> None:
    """Translate a Ludus HTTP response into the appropriate typed exception.

    This is the single place where HTTP status codes are converted to
    `LudusError` subclasses. Callers pass `on_conflict_user_exists=True`
    for user_add so that 409 becomes `LudusUserExists` (Ludus actually
    uses 400 for "User with that ID already exists", so we treat 400
    containing "already exists" the same way for robustness).
    """
    status = response.status_code
    if 200 <= status < 300:
        return

    detail = _extract_error_detail(response)

    if status in (401, 403):
        raise LudusAuthError(detail, status_code=status)
    if status == 404:
        raise LudusNotFound(detail, status_code=status)
    if on_conflict_user_exists and (
        status == 409 or (status == 400 and "already exists" in detail.lower())
    ):
        raise LudusUserExists(detail, status_code=status)
    if status == 409:
        # Generic conflict - e.g. deployment already running.
        raise LudusError(detail, status_code=status)

    raise LudusError(detail, status_code=status)


def _user_params(user_id: str | None, **extra: Any) -> dict[str, Any] | None:
    """Build a query-param dict for admin impersonation (``?userID=``).

    Returns ``None`` when there are no params so httpx omits the query
    string entirely (acting as the API key's own user).
    """
    params: dict[str, Any] = {}
    if user_id is not None:
        params["userID"] = user_id
    for key, value in extra.items():
        if value is not None:
            params[key] = value
    return params or None


class LudusClient:
    """Synchronous HTTP wrapper for the Ludus v1 REST API.

    The client is intentionally thin - each method maps to one logical
    Ludus operation and never leaks `httpx` types to callers. Errors are
    always raised as subclasses of `LudusError`. Operations that do not
    exist on Ludus v1 raise `LudusNotSupported`.
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        verify_tls: bool = False,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        # Allow dependency injection for tests (e.g. httpx.MockTransport).
        if client is not None:
            self._client = client
        else:
            # Note: we intentionally do NOT set a default Content-Type
            # header on the Client. httpx auto-generates the correct
            # value per request (application/json when `json=` is set,
            # multipart/form-data with a unique boundary when `files=`
            # is set). Setting a default header would override the
            # multipart boundary and break uploads.
            self._client = httpx.Client(
                base_url=self._url,
                verify=verify_tls,
                timeout=timeout,
                headers={
                    "X-API-KEY": api_key,
                    "Accept": "application/json",
                },
            )
        self._owns_client = client is None
        logger.debug("LudusClient initialised for %s", self._url)

    # -- context manager / lifecycle -------------------------------------

    def __enter__(self) -> LudusClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying httpx client if we own it."""
        if self._owns_client:
            self._client.close()

    # -- low-level helpers -----------------------------------------------

    @staticmethod
    def _safe_url_for_log(path: str) -> str:
        """Return a path without any query string - avoids leaking userIDs
        or other parameters into logs."""
        return path.split("?", 1)[0]

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        on_conflict_user_exists: bool = False,
    ) -> httpx.Response:
        """Dispatch a request through the shared httpx.Client.

        Handles timeout translation and delegates status checking to
        `_raise_for_status`. Never logs the api key or raw query string.
        """
        try:
            response = self._client.request(
                method,
                path,
                json=json,
                params=params,
                files=files,
                data=data,
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "Ludus request timed out: %s %s",
                method,
                self._safe_url_for_log(path),
            )
            raise LudusTimeout(f"Ludus request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            logger.warning(
                "Ludus request transport error: %s %s",
                method,
                self._safe_url_for_log(path),
            )
            raise LudusError(f"Ludus transport error: {exc}") from exc

        logger.debug(
            "Ludus %s %s -> %d",
            method,
            self._safe_url_for_log(path),
            response.status_code,
        )
        _raise_for_status(response, on_conflict_user_exists=on_conflict_user_exists)
        return response

    def _json(self, response: httpx.Response, op: str) -> Any:
        """Parse a JSON response body or raise a descriptive LudusError."""
        try:
            return response.json()
        except ValueError as exc:
            raise LudusError(
                f"Ludus returned invalid JSON for {op}",
                status_code=response.status_code,
            ) from exc

    @staticmethod
    def _as_list(data: Any) -> list[dict]:
        """Normalise a list-or-single-object response to a list of dicts."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    @staticmethod
    def _unwrap_result_str(response: httpx.Response) -> str:
        """Return a string payload from a ``{"result": "..."}`` envelope
        or raw text, whichever the server sent."""
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = response.json()
            except ValueError:
                return response.text
            if isinstance(body, dict):
                result = body.get("result")
                if isinstance(result, str):
                    return result
            return response.text
        return response.text

    # -- user management -------------------------------------------------

    def user_add(self, userid: str, name: str, email: str, *, is_admin: bool = False) -> dict:
        """Create a Ludus user.

        Route:  POST /user   body {userID, name, email, isAdmin}
        The response contains the user's plaintext ``apiKey`` (only ever
        returned here; otherwise reset via /user/apikey).

        Raises LudusUserExists on 400/409 "already exists", LudusAuthError
        on 401/403, LudusError otherwise.
        """
        payload = {
            "userID": userid,
            "name": name,
            "email": email,
            "isAdmin": is_admin,
        }
        response = self._request(
            "POST",
            f"{API_BASE}/user",
            json=payload,
            on_conflict_user_exists=True,
        )
        data = self._json(response, "user_add")
        if not isinstance(data, dict):
            raise LudusError(
                f"Unexpected user_add response shape: {type(data).__name__}",
                status_code=response.status_code,
            )
        return data

    def user_rm(self, userid: str) -> None:
        """Delete a Ludus user.  Route: DELETE /user/{userID}."""
        self._request("DELETE", f"{API_BASE}/user/{userid}")

    def user_list(self) -> list[dict]:
        """List all users.  Route: GET /user/all -> list of user dicts."""
        response = self._request("GET", f"{API_BASE}/user/all")
        return self._as_list(self._json(response, "user_list"))

    def user_wireguard(self, userid: str) -> str:
        """Return the WireGuard .conf text for a user.

        Route:  GET /user/wireguard?userID=<id>
        Response: JSON ``{"result": {"wireGuardConfig": "<...>"}}`` (verified),
        with a raw-text fallback for older/alternate builds.
        """
        response = self._request(
            "GET",
            f"{API_BASE}/user/wireguard",
            params={"userID": userid},
        )
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body = self._json(response, "user_wireguard")
            if isinstance(body, dict):
                result = body.get("result")
                if isinstance(result, dict):
                    cfg = result.get("wireGuardConfig")
                    if isinstance(cfg, str):
                        return cfg
                cfg = body.get("wireGuardConfig")
                if isinstance(cfg, str):
                    return cfg
            raise LudusError(
                "Ludus user_wireguard response missing wireGuardConfig",
                status_code=response.status_code,
            )
        return response.text

    # -- range sharing (cross-range access) ------------------------------

    def range_access_grant(
        self,
        source_user_id: str,
        target_user_id: str,
        *,
        force: bool = False,
    ) -> dict:
        """Grant *source_user_id* access to *target_user_id*'s range.

        This is Ludus v1's range-sharing mechanism (there is no
        range-assignment endpoint). ``target_user_id`` is the owner of the
        shared range; ``source_user_id`` is the user gaining access.

        Route:  POST /range/access
        Body:   {"action":"grant","sourceUserID","targetUserID","force"}
        """
        body = {
            "action": "grant",
            "sourceUserID": source_user_id,
            "targetUserID": target_user_id,
            "force": force,
        }
        response = self._request("POST", f"{API_BASE}/range/access", json=body)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_access_revoke(
        self,
        source_user_id: str,
        target_user_id: str,
        *,
        force: bool = False,
    ) -> dict:
        """Revoke *source_user_id*'s access to *target_user_id*'s range.

        Route:  POST /range/access
        Body:   {"action":"revoke","sourceUserID","targetUserID","force"}
        """
        body = {
            "action": "revoke",
            "sourceUserID": source_user_id,
            "targetUserID": target_user_id,
            "force": force,
        }
        response = self._request("POST", f"{API_BASE}/range/access", json=body)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_access_list(self) -> list[dict]:
        """List active cross-range accesses.  Route: GET /range/access."""
        response = self._request("GET", f"{API_BASE}/range/access")
        return self._as_list(self._json(response, "range_access_list"))

    # -- range deploy / config / lifecycle -------------------------------

    def range_deploy(self, userid: str, config_yaml: str) -> None:
        """Upload a range config and deploy it for *userid*.

        Two-step Ludus flow:
            1. PUT  /range/config?userID=<id>   multipart file=<yaml>, force=true
            2. POST /range/deploy?userID=<id>   body {}
        """
        params = {"userID": userid}
        self._request(
            "PUT",
            f"{API_BASE}/range/config",
            params=params,
            files={"file": ("range-config.yml", config_yaml, "application/x-yaml")},
            data={"force": "true"},
        )
        self._request(
            "POST",
            f"{API_BASE}/range/deploy",
            params=params,
            json={},
        )

    def range_deploy_existing(self, *, user_id: str | None = None) -> None:
        """Deploy an already-configured range.  Route: POST /range/deploy?userID=."""
        self._request(
            "POST",
            f"{API_BASE}/range/deploy",
            params=_user_params(user_id),
            json={},
        )

    def range_list(self) -> list[dict]:
        """List summary info for all ranges.  Route: GET /range/all.

        Each item is ``{userID, rangeNumber, lastDeployment, numberOfVMs,
        testingEnabled, rangeState, ...}``.
        """
        response = self._request("GET", f"{API_BASE}/range/all")
        return self._as_list(self._json(response, "range_list"))

    def range_get_config(self, *, user_id: str | None = None) -> str:
        """Return the range-config YAML for a user's range.

        Route:  GET /range/config?userID=<id>  -> {"result": "<yaml>"} or raw.
        """
        response = self._request(
            "GET",
            f"{API_BASE}/range/config",
            params=_user_params(user_id),
        )
        return self._unwrap_result_str(response)

    def range_get_vms(self, *, user_id: str | None = None) -> dict:
        """Return a user's range with VM power/state.

        Route:  GET /range?userID=<id>
        Response is a single object: ``{userID, rangeNumber, numberOfVMs,
        testingEnabled, rangeState, VMs:[{ID, proxmoxID, name, poweredOn,
        ip}], ...}``.
        """
        response = self._request("GET", f"{API_BASE}/range", params=_user_params(user_id))
        data = self._json(response, "range_get_vms")
        if isinstance(data, dict):
            return data
        raise LudusError(
            f"Unexpected range_get_vms response shape: {type(data).__name__}",
            status_code=response.status_code,
        )

    def range_destroy(self, *, user_id: str | None = None, force: bool = False) -> None:
        """Destroy a user's range (all VMs).  Route: DELETE /range?userID=[&force=]."""
        self._request(
            "DELETE",
            f"{API_BASE}/range",
            params=_user_params(user_id, force=True if force else None),
        )

    def range_abort(self, *, user_id: str | None = None) -> dict:
        """Abort a running deployment.  Route: POST /range/abort?userID=."""
        response = self._request("POST", f"{API_BASE}/range/abort", params=_user_params(user_id))
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_tags(self) -> list[str]:
        """List available deploy tags.  Route: GET /range/tags -> {tags:[...]}."""
        response = self._request("GET", f"{API_BASE}/range/tags")
        data = self._json(response, "range_tags")
        if isinstance(data, dict):
            return data.get("tags", [])
        if isinstance(data, list):
            return data
        return []

    def range_config_example(self) -> str:
        """Return an example range config.  Route: GET /range/config/example."""
        response = self._request("GET", f"{API_BASE}/range/config/example")
        return self._unwrap_result_str(response)

    # -- power management ------------------------------------------------

    def range_power_on(
        self,
        user_id: str | None = None,
        *,
        machines: list[str] | None = None,
    ) -> None:
        """Power on VMs.  Route: PUT /range/poweron?userID=  body {machines}."""
        self._request(
            "PUT",
            f"{API_BASE}/range/poweron",
            params=_user_params(user_id),
            json={"machines": machines or ["all"]},
        )

    def range_power_off(
        self,
        user_id: str | None = None,
        *,
        machines: list[str] | None = None,
    ) -> None:
        """Power off VMs.  Route: PUT /range/poweroff?userID=  body {machines}."""
        self._request(
            "PUT",
            f"{API_BASE}/range/poweroff",
            params=_user_params(user_id),
            json={"machines": machines or ["all"]},
        )

    # -- snapshot management ---------------------------------------------

    def snapshot_list(self, *, user_id: str | None = None) -> list[dict]:
        """List snapshots for a user's range.

        Route:  GET /snapshots/list?userID=<id>
        Response: ``{"errors": ..., "snapshots": [ {name, includesRAM,
        description, snaptime, parent, vmid, vmname}, ... ]}``.  Returns the
        inner ``snapshots`` list.
        """
        response = self._request(
            "GET",
            f"{API_BASE}/snapshots/list",
            params=_user_params(user_id),
        )
        data = self._json(response, "snapshot_list")
        if isinstance(data, dict):
            snaps = data.get("snapshots")
            if isinstance(snaps, list):
                return snaps
            return []
        return self._as_list(data)

    def snapshot_create(
        self,
        name: str,
        *,
        user_id: str | None = None,
        description: str = "",
        include_ram: bool = True,
        vmids: list[int] | None = None,
    ) -> dict:
        """Create a snapshot.  Route: POST /snapshots/create?userID=.

        Note: Ludus v1 includes RAM by default (CLI ``--noRAM`` to exclude),
        so ``include_ram`` defaults to True to match server behaviour.
        ``vmids`` limits to specific Proxmox VM IDs (default: all in range).
        """
        body: dict[str, Any] = {
            "name": name,
            "description": description,
            "includeRAM": include_ram,
        }
        if vmids is not None:
            body["vmIDs"] = vmids
        response = self._request(
            "POST",
            f"{API_BASE}/snapshots/create",
            params=_user_params(user_id),
            json=body,
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def snapshot_revert(
        self,
        name: str,
        *,
        user_id: str | None = None,
        vmids: list[int] | None = None,
    ) -> None:
        """Revert a range to a named snapshot.

        Route:  POST /snapshots/rollback?userID=<id>  body {name, vmIDs?}
        """
        body: dict[str, Any] = {"name": name}
        if vmids is not None:
            body["vmIDs"] = vmids
        self._request(
            "POST",
            f"{API_BASE}/snapshots/rollback",
            params=_user_params(user_id),
            json=body,
        )

    def snapshot_delete(
        self,
        name: str,
        *,
        user_id: str | None = None,
        vmids: list[int] | None = None,
    ) -> None:
        """Delete a snapshot.  Route: POST /snapshots/remove?userID=  body {name, vmIDs?}."""
        body: dict[str, Any] = {"name": name}
        if vmids is not None:
            body["vmIDs"] = vmids
        self._request(
            "POST",
            f"{API_BASE}/snapshots/remove",
            params=_user_params(user_id),
            json=body,
        )

    # -- testing state management ----------------------------------------

    def testing_start(self, *, user_id: str | None = None) -> dict:
        """Enter testing mode.  Route: PUT /testing/start?userID=."""
        response = self._request("PUT", f"{API_BASE}/testing/start", params=_user_params(user_id))
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_stop(self, *, user_id: str | None = None, force: bool = False) -> dict:
        """Exit testing mode.  Route: PUT /testing/stop?userID=  body {force?}."""
        body: dict[str, Any] = {}
        if force:
            body["force"] = True
        response = self._request(
            "PUT",
            f"{API_BASE}/testing/stop",
            params=_user_params(user_id),
            json=body or None,
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_allow(
        self,
        *,
        user_id: str | None = None,
        domains: list[str] | None = None,
        ips: list[str] | None = None,
    ) -> dict:
        """Allow domains/IPs during testing.  Route: POST /testing/allow?userID=."""
        body: dict[str, Any] = {}
        if domains is not None:
            body["domains"] = domains
        if ips is not None:
            body["ips"] = ips
        response = self._request(
            "POST",
            f"{API_BASE}/testing/allow",
            params=_user_params(user_id),
            json=body,
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_deny(
        self,
        *,
        user_id: str | None = None,
        domains: list[str] | None = None,
        ips: list[str] | None = None,
    ) -> dict:
        """Deny domains/IPs during testing.  Route: POST /testing/deny?userID=."""
        body: dict[str, Any] = {}
        if domains is not None:
            body["domains"] = domains
        if ips is not None:
            body["ips"] = ips
        response = self._request(
            "POST",
            f"{API_BASE}/testing/deny",
            params=_user_params(user_id),
            json=body,
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_update(self, name: str, *, user_id: str | None = None) -> dict:
        """Update a VM/group's testing config.  Route: POST /testing/update?userID=."""
        response = self._request(
            "POST",
            f"{API_BASE}/testing/update",
            params=_user_params(user_id),
            json={"name": name},
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    # -- template management ---------------------------------------------

    def template_list(self) -> list[dict]:
        """List VM templates.  Route: GET /templates."""
        response = self._request("GET", f"{API_BASE}/templates")
        return self._as_list(self._json(response, "template_list"))

    def template_delete(self, name: str) -> None:
        """Delete a template.  Route: DELETE /template/{name}."""
        self._request("DELETE", f"{API_BASE}/template/{name}")

    def template_build(self, templates: list[str], *, parallel: int = 1) -> None:
        """Build templates via Packer.  Route: POST /templates  body {templates, parallel}."""
        self._request(
            "POST",
            f"{API_BASE}/templates",
            json={"templates": templates, "parallel": parallel},
        )

    def template_abort(self) -> None:
        """Abort a running Packer build.  Route: POST /templates/abort."""
        self._request("POST", f"{API_BASE}/templates/abort")

    def template_status(self) -> list[dict]:
        """Get the Packer build queue/status.  Route: GET /templates/status."""
        response = self._request("GET", f"{API_BASE}/templates/status")
        return self._as_list(self._json(response, "template_status"))

    def template_logs(self) -> str:
        """Get live Packer build logs.  Route: GET /templates/logs."""
        response = self._request("GET", f"{API_BASE}/templates/logs")
        return self._unwrap_result_str(response)

    # -- range detail (read-only) ----------------------------------------

    def range_logs(self, *, user_id: str | None = None, tail: int | None = None) -> dict:
        """Get the latest deploy logs.  Route: GET /range/logs?userID=[&tail=]."""
        response = self._request(
            "GET",
            f"{API_BASE}/range/logs",
            params=_user_params(user_id, tail=tail),
        )
        try:
            return response.json()
        except ValueError:
            return {"result": response.text}

    def range_etchosts(self, *, user_id: str | None = None) -> str:
        """Get /etc/hosts for a range.  Route: GET /range/etchosts?userID=."""
        response = self._request("GET", f"{API_BASE}/range/etchosts", params=_user_params(user_id))
        return self._unwrap_result_str(response)

    def range_sshconfig(self) -> str:
        """Get the SSH config for the range.  Route: GET /range/sshconfig."""
        response = self._request("GET", f"{API_BASE}/range/sshconfig")
        return self._unwrap_result_str(response)

    def range_rdpconfigs(self, *, user_id: str | None = None) -> bytes:
        """Get RDP configs as a zip.  Route: GET /range/rdpconfigs?userID=."""
        response = self._request(
            "GET", f"{API_BASE}/range/rdpconfigs", params=_user_params(user_id)
        )
        return response.content

    def range_ansibleinventory(self, *, user_id: str | None = None) -> str:
        """Get the Ansible inventory.  Route: GET /range/ansibleinventory?userID=."""
        response = self._request(
            "GET", f"{API_BASE}/range/ansibleinventory", params=_user_params(user_id)
        )
        return self._unwrap_result_str(response)

    # -- ansible management ----------------------------------------------

    def ansible_list(self, *, user_id: str | None = None) -> list[dict]:
        """List installed roles/collections.  Route: GET /ansible?userID=."""
        response = self._request("GET", f"{API_BASE}/ansible", params=_user_params(user_id))
        return self._as_list(self._json(response, "ansible_list"))

    def ansible_role(
        self,
        role: str,
        action: str = "install",
        *,
        version: str = "",
        force: bool = False,
        global_: bool = False,
    ) -> dict:
        """Install or remove an Ansible role.

        Route:  POST /ansible/role
        Body:   {"role","action":"install"|"remove","global","force","version"}

        On Ludus v1, installing a role globally (``global_=True``) is the way
        to make it available to all users - there is no separate role-scope
        endpoint.
        """
        body: dict[str, Any] = {
            "role": role,
            "action": action,
            "global": global_,
            "force": force,
            "version": version,
        }
        response = self._request("POST", f"{API_BASE}/ansible/role", json=body)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def ansible_collection(
        self,
        collection: str,
        *,
        version: str | None = None,
        force: bool = False,
    ) -> dict:
        """Install an Ansible collection.  Route: POST /ansible/collection."""
        body: dict[str, Any] = {"collection": collection}
        if version is not None:
            body["version"] = version
        if force:
            body["force"] = True
        response = self._request("POST", f"{API_BASE}/ansible/collection", json=body)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def ansible_role_from_tar(
        self,
        file_data: bytes,
        filename: str,
        *,
        force: bool = False,
    ) -> dict:
        """Install a role from a tar file.  Route: PUT /ansible/role/fromtar."""
        files_payload = {"file": (filename, file_data, "application/gzip")}
        data_payload: dict[str, str] = {}
        if force:
            data_payload["force"] = "true"
        response = self._request(
            "PUT",
            f"{API_BASE}/ansible/role/fromtar",
            files=files_payload,
            data=data_payload or None,
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def ansible_scope_roles_global(self, roles: list[str], *, force: bool = False) -> None:
        """Make each role in *roles* global (available to all users).

        Ludus v1 has no ``/ansible/role/scope`` endpoint; the equivalent is
        (re)installing the role with ``global=True``. Raises ``LudusError`` if
        any role fails so the caller can record/handle it (provisioning treats
        this as non-fatal and emits a ``session.role_scope_failed`` event).
        """
        for role in roles:
            self.ansible_role(role, action="install", global_=True, force=force)

    # -- operations NOT supported on Ludus v1 ----------------------------

    def _unsupported(self, name: str, alternative: str = "") -> LudusNotSupported:
        msg = f"'{name}' is not available on Ludus v1"
        if alternative:
            msg += f" ({alternative})"
        return LudusNotSupported(msg)

    def range_assign(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported(
            "range_assign", "use range_access_grant(source_user_id, target_user_id)"
        )

    def range_revoke(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported(
            "range_revoke", "use range_access_revoke(source_user_id, target_user_id)"
        )

    def range_users(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("range_users", "use range_access_list()")

    def range_create(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("range_create", "v1 is single-range-per-user")

    def ranges_accessible(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("ranges_accessible", "use range_access_list()")

    def range_delete_vms(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("range_delete_vms", "use range_destroy(force=True)")

    def vm_destroy(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("vm_destroy", "v1 has no per-VM delete endpoint")

    def range_logs_history(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("range_logs_history")

    def range_log_entry(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("range_log_entry")

    def whoami(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("whoami")

    def group_create(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("groups", "group management was added after v1")

    # All group operations are unsupported on v1; alias them to one raiser.
    group_list = group_delete = group_users = group_add_users = group_create
    group_remove_users = group_ranges = group_add_ranges = group_remove_ranges = group_create

    def ansible_subscription_roles(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("ansible_subscription_roles")

    def ansible_install_subscription_roles(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("ansible_install_subscription_roles")

    def ansible_role_vars(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported("ansible_role_vars")

    def ansible_role_scope(self, *args: Any, **kwargs: Any) -> None:
        raise self._unsupported(
            "ansible_role_scope", "use ansible_scope_roles_global(roles) on v1"
        )


def get_ludus_client() -> LudusClient:
    """FastAPI dependency: build a `LudusClient` from app settings."""
    settings = get_settings()
    return LudusClient(
        url=settings.ludus_default_url,
        api_key=settings.ludus_default_api_key,
        verify_tls=settings.ludus_default_verify_tls,
    )
