"""Single integration point between the platform and a Ludus server.

Every Ludus HTTP call in the backend MUST go through `LudusClient`. This
makes it trivial to:

* swap transports (CLI -> HTTP -> future gRPC)
* apply retries / timeouts / logging in one place
* mock Ludus in tests

================================================================
ASSUMED HTTP ROUTES — verified against badsectorlabs/ludus Go source
(ludus-api/routers.go, ludus-api/api_user_management.go, etc.)
See issue #TODO to pin these once tested against a live Ludus instance.
================================================================

Base path:              /api/v2
Auth header:            X-API-KEY: <api_key>
Admin impersonation:    append ?userID=<userID> query param (admin key only)

Routes used here:
    POST   /api/v2/user                                   -> user_add
           body: {"userID", "name", "email", "password", "isAdmin"}
    DELETE /api/v2/user/{userID}                          -> user_rm
    GET    /api/v2/user/all                               -> user_list
    POST   /api/v2/ranges/assign/{userID}/{rangeID}       -> range_assign
    GET    /api/v2/user/wireguard?userID=<userID>         -> user_wireguard
           returns JSON {"result": {"wireGuardConfig": "<.conf text>"}}
    POST   /api/v2/snapshots/rollback?userID=<userID>     -> snapshot_revert
           body: {"name": "<snapshot>", "vmIDs": [...]}
    GET    /api/v2/snapshots/list?userID=                 -> snapshot_list
    POST   /api/v2/snapshots/create?userID=               -> snapshot_create
           body: {"name", "description", "includeRAM", "vmIDs"}
    POST   /api/v2/snapshots/remove?userID=               -> snapshot_delete
           body: {"name", "vmIDs": [...]}
    PUT    /api/v2/range/config?userID=<userID>           -> range_deploy (step 1)
           multipart form: file=<range-config.yml>, force=true
    POST   /api/v2/range/deploy?userID=<userID>           -> range_deploy (step 2)
           body: {"force": false}
    POST   /api/v2/range/deploy?rangeNumber=<N>           -> range_deploy_existing
    DELETE /api/v2/range?rangeNumber=<N>                  -> range_destroy
    GET    /api/v2/range/all                              -> range_list
    GET    /api/v2/range/config?userID=|rangeNumber=      -> range_get_config
    PUT    /api/v2/range/poweron?userID=                  -> range_power_on
           body: {"machines": ["all"]}
    PUT    /api/v2/range/poweroff?userID=                 -> range_power_off
           body: {"machines": ["all"]}
    GET    /api/v2/templates                              -> template_list
    POST   /api/v2/templates                              -> template_build
           body: {"templates": [...], "parallel": N}
    POST   /api/v2/templates/abort                        -> template_abort
    GET    /api/v2/templates/status                       -> template_status
    GET    /api/v2/templates/logs                         -> template_logs
    DELETE /api/v2/template/{name}                        -> template_delete
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
    LudusTimeout,
    LudusUserExists,
)

logger = logging.getLogger(__name__)

API_BASE = "/api/v2"


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
        # Generic conflict — e.g. deployment already running.
        raise LudusError(detail, status_code=status)

    raise LudusError(detail, status_code=status)


class LudusClient:
    """Synchronous HTTP wrapper for the Ludus REST API (v2).

    The client is intentionally thin — each method maps to one logical
    Ludus operation and never leaks `httpx` types to callers. Errors are
    always raised as subclasses of `LudusError`.
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
        """Return a path without any query string — avoids leaking userIDs
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
            # httpx sets Content-Type automatically per request:
            #   - application/json when `json=` is provided
            #   - multipart/form-data (with boundary) when `files=` is provided
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

    # -- user management -------------------------------------------------

    def user_add(self, userid: str, name: str, email: str) -> dict:
        """Create a Ludus user.

        Route:  POST /api/v2/user
        Body:   {"userID", "name", "email", "isAdmin": false}
        Raises:
            LudusAuthError on 401/403.
            LudusUserExists on 409 (or 400 "already exists").
            LudusError on any other non-2xx.
        Returns:
            The parsed JSON response (typically containing userID, apiKey, ...).
        """
        payload = {
            "userID": userid,
            "name": name,
            "email": email,
            "isAdmin": False,
        }
        response = self._request(
            "POST",
            f"{API_BASE}/user",
            json=payload,
            on_conflict_user_exists=True,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                f"Ludus returned non-JSON on user_add: {response.text!r}",
                status_code=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise LudusError(
                f"Unexpected user_add response shape: {type(data).__name__}",
                status_code=response.status_code,
            )
        return data

    def user_rm(self, userid: str) -> None:
        """Delete a Ludus user.

        Route:  DELETE /api/v2/user/{userID}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        """
        self._request("DELETE", f"{API_BASE}/user/{userid}")

    # -- range access / deploy ------------------------------------------

    def range_assign(self, userid: str, range_id: str) -> None:
        """Grant `userid` access to an existing range.

        Route:  POST /api/v2/ranges/assign/{userID}/{rangeID}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404 (user or range missing).
            LudusError on any other non-2xx.
        """
        self._request(
            "POST",
            f"{API_BASE}/ranges/assign/{userid}/{range_id}",
        )

    def user_wireguard(self, userid: str) -> str:
        """Return the WireGuard .conf file text for a user.

        Route:  GET /api/v2/user/wireguard?userID=<userID>
        Response: JSON {"result": {"wireGuardConfig": "<[Interface]...>"}}

        Admin impersonation via the `?userID=` query param is the only
        supported way to fetch another user's config using the platform's
        admin API key. Ludus also supports calling this as the target
        user directly, but the platform always acts as admin.

        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError if the response is not JSON with the expected shape.
        Returns:
            The raw `.conf` file contents.
        """
        response = self._request(
            "GET",
            f"{API_BASE}/user/wireguard",
            params={"userID": userid},
        )

        # Response can be JSON wrapping the config, or — depending on the
        # Ludus version — the raw file. Handle both.
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = response.json()
            except ValueError as exc:
                raise LudusError(
                    "Ludus returned invalid JSON for user_wireguard",
                    status_code=response.status_code,
                ) from exc
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
        # Fall back to raw text (e.g. octet-stream, text/plain).
        return response.text

    def snapshot_revert(
        self,
        userid: str,
        name: str,
        *,
        vmids: list[int] | None = None,
        range_id: str | None = None,
    ) -> None:
        """Revert the user's range to a named snapshot.

        Route:  POST /api/v2/snapshots/rollback?userID=<userID>[&rangeID=<rangeID>]
        Body:   {"name": "<snapshot_name>", "vmIDs": [...]}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404 (snapshot or range missing).
            LudusError on any other non-2xx.
        """
        body: dict[str, Any] = {"name": name}
        if vmids is not None:
            body["vmIDs"] = vmids
        params: dict[str, str] = {"userID": userid}
        if range_id is not None:
            params["rangeID"] = range_id
        self._request(
            "POST",
            f"{API_BASE}/snapshots/rollback",
            params=params,
            json=body,
        )

    def range_deploy(self, userid: str, config_yaml: str) -> None:
        """Deploy a new range for the user from raw range-config YAML.

        This is a two-step Ludus flow:
            1. PUT  /api/v2/range/config?userID=<userID>
               multipart form: file=<range-config.yml>, force=true
            2. POST /api/v2/range/deploy?userID=<userID>
               body: {}

        Raises:
            LudusAuthError on 401/403 in either step.
            LudusNotFound on 404.
            LudusError on any other non-2xx (e.g. invalid YAML -> 400).
        """
        params = {"userID": userid}

        # Step 1: upload the range config.
        self._request(
            "PUT",
            f"{API_BASE}/range/config",
            params=params,
            files={"file": ("range-config.yml", config_yaml, "application/x-yaml")},
            data={"force": "true"},
        )

        # Step 2: kick off the deployment.
        self._request(
            "POST",
            f"{API_BASE}/range/deploy",
            params=params,
            json={},
        )

    def range_list(self) -> list[dict]:
        """List all ranges visible to the current API key.

        Route:  GET /api/v2/range/all
        Raises:
            LudusAuthError on 401/403.
            LudusError on any other non-2xx.
        Returns:
            A list of range dicts. If Ludus returns a single range object,
            it is wrapped in a one-element list for caller convenience.
        """
        response = self._request("GET", f"{API_BASE}/range/all")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for range_list",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        raise LudusError(
            f"Unexpected range_list response shape: {type(data).__name__}",
            status_code=response.status_code,
        )

    def range_get_config(
        self,
        *,
        user_id: str | None = None,
        range_number: int | None = None,
    ) -> str:
        """Return the range-config YAML for a range.

        Route:  GET /api/v2/range/config?userID=<userID>
            or  GET /api/v2/range/config?rangeNumber=<N>

        Exactly one of ``user_id`` or ``range_number`` must be provided.

        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404 (user or range missing).
            LudusError on any other non-2xx or unexpected response shape.
        Returns:
            The raw YAML string.
        """
        if (user_id is None) == (range_number is None):
            raise ValueError("Exactly one of user_id or range_number must be provided")

        params: dict[str, str | int] = {}
        if user_id is not None:
            params["userID"] = user_id
        else:
            assert range_number is not None
            params["rangeNumber"] = range_number

        response = self._request(
            "GET",
            f"{API_BASE}/range/config",
            params=params,
        )

        # Response can be JSON wrapping the config, or raw text — handle
        # both the same way as user_wireguard.
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = response.json()
            except ValueError as exc:
                raise LudusError(
                    "Ludus returned invalid JSON for range_get_config",
                    status_code=response.status_code,
                ) from exc
            if isinstance(body, dict):
                result = body.get("result")
                if isinstance(result, str):
                    return result
                # Some versions nest under "rangeConfig"
                cfg = body.get("rangeConfig")
                if isinstance(cfg, str):
                    return cfg
            raise LudusError(
                "Ludus range_get_config response missing config data",
                status_code=response.status_code,
            )
        # Fall back to raw text (e.g. text/plain, application/x-yaml).
        return response.text

    # -- user listing --------------------------------------------------------

    def user_list(self) -> list[dict]:
        """List all users visible to the current API key.

        Route:  GET /api/v2/user/all
        Raises:
            LudusAuthError on 401/403.
            LudusError on any other non-2xx.
        Returns:
            A list of user dicts. If Ludus returns a single user object,
            it is wrapped in a one-element list for caller convenience.
        """
        response = self._request("GET", f"{API_BASE}/user/all")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for user_list",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        raise LudusError(
            f"Unexpected user_list response shape: {type(data).__name__}",
            status_code=response.status_code,
        )

    # -- range deploy (existing) / destroy ----------------------------------

    def range_deploy_existing(
        self,
        *,
        user_id: str | None = None,
        range_number: int | None = None,
    ) -> None:
        """Deploy an already-configured range.

        Route:  POST /api/v2/range/deploy?userID=<userID>
            or  POST /api/v2/range/deploy?rangeNumber=<N>

        Exactly one of ``user_id`` or ``range_number`` must be provided.

        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        """
        if (user_id is None) == (range_number is None):
            raise ValueError("Exactly one of user_id or range_number must be provided")

        params: dict[str, str | int] = {}
        if user_id is not None:
            params["userID"] = user_id
        else:
            assert range_number is not None
            params["rangeNumber"] = range_number

        self._request(
            "POST",
            f"{API_BASE}/range/deploy",
            params=params,
            json={},
        )

    def range_destroy(self, range_number: int, *, force: bool = False) -> None:
        """Destroy a range by its number.

        Route:  DELETE /api/v2/range?rangeNumber=<N>[&force=true]
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        """
        params: dict[str, int | bool] = {"rangeNumber": range_number}
        if force:
            params["force"] = True
        self._request(
            "DELETE",
            f"{API_BASE}/range",
            params=params,
        )

    # -- power management ----------------------------------------------------

    def range_power_on(self, user_id: str, *, machines: list[str] | None = None) -> None:
        """Power on VMs in a user's range.

        Route:  PUT /api/v2/range/poweron?userID=<userID>
        Body:   {"machines": ["all"]}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        """
        self._request(
            "PUT",
            f"{API_BASE}/range/poweron",
            params={"userID": user_id},
            json={"machines": machines or ["all"]},
        )

    def range_power_off(self, user_id: str, *, machines: list[str] | None = None) -> None:
        """Power off VMs in a user's range.

        Route:  PUT /api/v2/range/poweroff?userID=<userID>
        Body:   {"machines": ["all"]}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        """
        self._request(
            "PUT",
            f"{API_BASE}/range/poweroff",
            params={"userID": user_id},
            json={"machines": machines or ["all"]},
        )

    # -- snapshot management -------------------------------------------------

    def snapshot_list(
        self,
        *,
        user_id: str | None = None,
        range_number: int | None = None,
        range_id: str | None = None,
    ) -> list[dict]:
        """List snapshots for a user or range.

        Route:  GET /api/v2/snapshots/list?userID=<userID>[&rangeID=<rangeID>]
            or  GET /api/v2/snapshots/list?rangeNumber=<N>

        At most one of ``user_id`` or ``range_number`` should be provided.
        If neither is given, lists snapshots for the admin user.

        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        Returns:
            A list of snapshot dicts.
        """
        params: dict[str, str | int] = {}
        if user_id is not None:
            params["userID"] = user_id
        if range_number is not None:
            params["rangeNumber"] = range_number
        if range_id is not None:
            params["rangeID"] = range_id

        response = self._request(
            "GET",
            f"{API_BASE}/snapshots/list",
            params=params or None,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for snapshot_list",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        raise LudusError(
            f"Unexpected snapshot_list response shape: {type(data).__name__}",
            status_code=response.status_code,
        )

    def snapshot_create(
        self,
        user_id: str,
        name: str,
        *,
        description: str = "",
        include_ram: bool = False,
        vmids: list[int] | None = None,
        range_id: str | None = None,
    ) -> None:
        """Create a snapshot for a user's range.

        Route:  POST /api/v2/snapshots/create?userID=<userID>[&rangeID=<rangeID>]
        Body:   {"name", "description", "includeRAM", "vmIDs"}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        """
        body: dict[str, Any] = {
            "name": name,
            "description": description,
            "includeRAM": include_ram,
        }
        if vmids is not None:
            body["vmIDs"] = vmids
        params: dict[str, str] = {"userID": user_id}
        if range_id is not None:
            params["rangeID"] = range_id
        self._request(
            "POST",
            f"{API_BASE}/snapshots/create",
            params=params,
            json=body,
        )

    def snapshot_delete(
        self,
        user_id: str,
        name: str,
        *,
        vmids: list[int] | None = None,
        range_id: str | None = None,
    ) -> None:
        """Delete a snapshot from a user's range.

        Route:  POST /api/v2/snapshots/remove?userID=<userID>[&rangeID=<rangeID>]
        Body:   {"name": "<snapshot>", "vmIDs": [...]}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404 (snapshot not found).
            LudusError on any other non-2xx.
        """
        body: dict[str, Any] = {"name": name}
        if vmids is not None:
            body["vmIDs"] = vmids
        params: dict[str, str] = {"userID": user_id}
        if range_id is not None:
            params["rangeID"] = range_id
        self._request(
            "POST",
            f"{API_BASE}/snapshots/remove",
            params=params,
            json=body,
        )

    # -- template management -------------------------------------------------

    def template_list(self) -> list[dict]:
        """List all VM templates available on the Ludus server.

        Route:  GET /api/v2/templates
        Raises:
            LudusAuthError on 401/403.
            LudusError on any other non-2xx.
        Returns:
            A list of template dicts.
        """
        response = self._request("GET", f"{API_BASE}/templates")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for template_list",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        raise LudusError(
            f"Unexpected template_list response shape: {type(data).__name__}",
            status_code=response.status_code,
        )

    def template_delete(self, name: str) -> None:
        """Delete a VM template by name.

        Route:  DELETE /api/v2/template/{name}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404.
            LudusError on any other non-2xx.
        """
        self._request("DELETE", f"{API_BASE}/template/{name}")

    def template_build(self, templates: list[str], *, parallel: int = 1) -> None:
        """Build VM templates via Packer.

        Route:  POST /api/v2/templates
        Body:   {"templates": [...], "parallel": N}
        Raises:
            LudusAuthError on 401/403.
            LudusError on any other non-2xx.
        """
        self._request(
            "POST",
            f"{API_BASE}/templates",
            json={"templates": templates, "parallel": parallel},
        )

    def template_abort(self) -> None:
        """Abort a running Packer template build.

        Route:  POST /api/v2/templates/abort
        Raises:
            LudusAuthError on 401/403.
            LudusError on any other non-2xx.
        """
        self._request("POST", f"{API_BASE}/templates/abort")

    def template_status(self) -> list[dict]:
        """Get the active template build queue.

        Route:  GET /api/v2/templates/status
        Returns:
            A list of dicts with ``template`` and ``user`` keys.
        Raises:
            LudusAuthError on 401/403.
            LudusError on any other non-2xx.
        """
        response = self._request("GET", f"{API_BASE}/templates/status")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for template_status",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def template_logs(self) -> str:
        """Get live Packer build log output.

        Route:  GET /api/v2/templates/logs
        Returns:
            Raw log text from the active build.
        Raises:
            LudusAuthError on 401/403.
            LudusError on any other non-2xx.
        """
        response = self._request("GET", f"{API_BASE}/templates/logs")
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
            return str(body)
        return response.text

    # -- range detail / VM operations ----------------------------------------

    def range_get_vms(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """Get VMs for a range with power/testing state.

        Route:  GET /api/v2/range
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request("GET", f"{API_BASE}/range", params=params or None)
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for range_get_vms",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        raise LudusError(
            f"Unexpected range_get_vms response shape: {type(data).__name__}",
            status_code=response.status_code,
        )

    def vm_destroy(self, vm_id: int) -> dict:
        """Destroy a single VM.

        Route:  DELETE /api/v2/vm/{vmID}
        """
        response = self._request("DELETE", f"{API_BASE}/vm/{vm_id}")
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_abort(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Abort a running range deployment.

        Route:  POST /api/v2/range/abort
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request("POST", f"{API_BASE}/range/abort", params=params or None)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_delete_vms(
        self,
        range_id: int,
        *,
        user_id: str | None = None,
    ) -> dict:
        """Delete all VMs in a range.

        Route:  DELETE /api/v2/range/{rangeID}/vms
        """
        params: dict[str, Any] = {}
        if user_id is not None:
            params["userID"] = user_id

        response = self._request(
            "DELETE", f"{API_BASE}/range/{range_id}/vms", params=params or None
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_tags(self) -> list[str]:
        """List all range tags.

        Route:  GET /api/v2/range/tags
        Returns: list of tag strings extracted from {"tags": [...]}
        """
        response = self._request("GET", f"{API_BASE}/range/tags")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for range_tags",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, dict):
            return data.get("tags", [])
        if isinstance(data, list):
            return data
        return []

    def range_config_example(self) -> str:
        """Get an example range config YAML.

        Route:  GET /api/v2/range/config/example
        """
        response = self._request("GET", f"{API_BASE}/range/config/example")
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
            return str(body)
        return response.text

    def range_logs(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
        tail: int | None = None,
        cursor: str | None = None,
    ) -> dict:
        """Get deployment logs for a range.

        Route:  GET /api/v2/range/logs
        Returns: dict with "result" and optional "cursor"
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id
        if tail is not None:
            params["tail"] = tail
        if cursor is not None:
            params["cursor"] = cursor

        response = self._request("GET", f"{API_BASE}/range/logs", params=params or None)
        try:
            return response.json()
        except ValueError:
            return {"result": response.text}

    def range_logs_history(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """Get deployment log history entries.

        Route:  GET /api/v2/range/logs/history
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request(
            "GET", f"{API_BASE}/range/logs/history", params=params or None
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for range_logs_history",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Ludus returns {"version": "...", "result": "..."} for
            # unrecognised routes — treat as empty history.
            if "version" in data:
                return []
            return [data]
        return []

    def range_log_entry(self, log_id: int) -> dict:
        """Get a specific deployment log entry.

        Route:  GET /api/v2/range/logs/history/{logID}
        """
        response = self._request("GET", f"{API_BASE}/range/logs/history/{log_id}")
        try:
            return response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for range_log_entry",
                status_code=response.status_code,
            ) from exc

    def range_etchosts(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> str:
        """Get /etc/hosts content for a range.

        Route:  GET /api/v2/range/etchosts
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request("GET", f"{API_BASE}/range/etchosts", params=params or None)
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
            return str(body)
        return response.text

    def range_sshconfig(self) -> str:
        """Get SSH config for the range.

        Route:  GET /api/v2/range/sshconfig
        """
        response = self._request("GET", f"{API_BASE}/range/sshconfig")
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
            return str(body)
        return response.text

    def range_rdpconfigs(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> bytes:
        """Get RDP configs as a zip file.

        Route:  GET /api/v2/range/rdpconfigs
        Returns: raw bytes (zip archive)
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request("GET", f"{API_BASE}/range/rdpconfigs", params=params or None)
        return response.content

    def range_ansibleinventory(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> str:
        """Get Ansible inventory YAML for a range.

        Route:  GET /api/v2/range/ansibleinventory
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request(
            "GET", f"{API_BASE}/range/ansibleinventory", params=params or None
        )
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
            return str(body)
        return response.text

    def range_create(
        self,
        name: str,
        range_id: int,
        **kwargs: Any,
    ) -> dict:
        """Create a new range.

        Route:  POST /api/v2/ranges/create
        """
        body: dict[str, Any] = {"name": name, "rangeID": range_id, **kwargs}
        response = self._request("POST", f"{API_BASE}/ranges/create", json=body)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_revoke(
        self,
        user_id: str,
        range_id: int,
        *,
        force: bool = False,
    ) -> dict:
        """Revoke a user's access to a range.

        Route:  DELETE /api/v2/ranges/revoke/{uID}/{rID}
        """
        params: dict[str, Any] = {}
        if force:
            params["force"] = "true"

        response = self._request(
            "DELETE",
            f"{API_BASE}/ranges/revoke/{user_id}/{range_id}",
            params=params or None,
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def range_users(self, range_id: int) -> list[dict]:
        """List users with access to a range.

        Route:  GET /api/v2/ranges/{rangeID}/users
        """
        response = self._request("GET", f"{API_BASE}/ranges/{range_id}/users")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for range_users",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def ranges_accessible(self) -> list[dict]:
        """List ranges accessible to the current user.

        Route:  GET /api/v2/ranges/accessible
        """
        response = self._request("GET", f"{API_BASE}/ranges/accessible")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for ranges_accessible",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    # -- testing state management --------------------------------------------

    def testing_start(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Enter testing mode for a range.

        Route:  PUT /api/v2/testing/start
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request("PUT", f"{API_BASE}/testing/start", params=params or None)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_stop(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
        force: bool = False,
    ) -> dict:
        """Exit testing mode for a range.

        Route:  PUT /api/v2/testing/stop
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        body: dict[str, Any] = {}
        if force:
            body["force"] = True

        response = self._request(
            "PUT", f"{API_BASE}/testing/stop", params=params or None, json=body or None
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_allow(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
        domains: list[str] | None = None,
        ips: list[str] | None = None,
    ) -> dict:
        """Allow domains/IPs during testing mode.

        Route:  POST /api/v2/testing/allow
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        body: dict[str, Any] = {}
        if domains is not None:
            body["domains"] = domains
        if ips is not None:
            body["ips"] = ips

        response = self._request(
            "POST", f"{API_BASE}/testing/allow", params=params or None, json=body
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_deny(
        self,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
        domains: list[str] | None = None,
        ips: list[str] | None = None,
    ) -> dict:
        """Deny domains/IPs during testing mode.

        Route:  POST /api/v2/testing/deny
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        body: dict[str, Any] = {}
        if domains is not None:
            body["domains"] = domains
        if ips is not None:
            body["ips"] = ips

        response = self._request(
            "POST", f"{API_BASE}/testing/deny", params=params or None, json=body
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def testing_update(
        self,
        name: str,
        *,
        range_id: int | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Update testing configuration.

        Route:  POST /api/v2/testing/update
        """
        params: dict[str, Any] = {}
        if range_id is not None:
            params["rangeNumber"] = range_id
        if user_id is not None:
            params["userID"] = user_id

        response = self._request(
            "POST",
            f"{API_BASE}/testing/update",
            params=params or None,
            json={"name": name},
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    # -- group management ----------------------------------------------------

    def group_create(self, name: str, *, description: str | None = None) -> dict:
        """Create a new group.

        Route:  POST /api/v2/groups
        """
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description

        response = self._request("POST", f"{API_BASE}/groups", json=body)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def group_list(self) -> list[dict]:
        """List all groups.

        Route:  GET /api/v2/groups
        """
        response = self._request("GET", f"{API_BASE}/groups")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for group_list",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def group_delete(self, group_name: str) -> None:
        """Delete a group.

        Route:  DELETE /api/v2/groups/{name}
        """
        self._request("DELETE", f"{API_BASE}/groups/{group_name}")

    def group_users(self, group_name: str) -> list[dict]:
        """List users in a group.

        Route:  GET /api/v2/groups/{name}/users
        """
        response = self._request("GET", f"{API_BASE}/groups/{group_name}/users")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for group_users",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def group_add_users(
        self,
        group_name: str,
        user_ids: list[str],
        *,
        managers: bool = False,
    ) -> dict:
        """Add users to a group.

        Route:  POST /api/v2/groups/{name}/users
        """
        body: dict[str, Any] = {"userIDs": user_ids}
        if managers:
            body["managers"] = True

        response = self._request(
            "POST", f"{API_BASE}/groups/{group_name}/users", json=body
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def group_remove_users(self, group_name: str, user_ids: list[str]) -> dict:
        """Remove users from a group.

        Route:  DELETE /api/v2/groups/{name}/users
        """
        response = self._request(
            "DELETE", f"{API_BASE}/groups/{group_name}/users", json={"userIDs": user_ids}
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def group_ranges(self, group_name: str) -> list[dict]:
        """List ranges assigned to a group.

        Route:  GET /api/v2/groups/{name}/ranges
        """
        response = self._request("GET", f"{API_BASE}/groups/{group_name}/ranges")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for group_ranges",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def group_add_ranges(self, group_name: str, range_ids: list[int]) -> dict:
        """Add ranges to a group.

        Route:  POST /api/v2/groups/{name}/ranges
        """
        response = self._request(
            "POST", f"{API_BASE}/groups/{group_name}/ranges", json={"rangeIDs": range_ids}
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def group_remove_ranges(self, group_name: str, range_ids: list[int]) -> dict:
        """Remove ranges from a group.

        Route:  DELETE /api/v2/groups/{name}/ranges
        """
        response = self._request(
            "DELETE",
            f"{API_BASE}/groups/{group_name}/ranges",
            json={"rangeIDs": range_ids},
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    # -- ansible management --------------------------------------------------

    def ansible_subscription_roles(self) -> list[dict]:
        """List subscription roles.

        Route:  GET /api/v2/ansible/subscription-roles
        """
        response = self._request("GET", f"{API_BASE}/ansible/subscription-roles")
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for ansible_subscription_roles",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def ansible_install_subscription_roles(
        self,
        roles: list[str],
        *,
        global_: bool = False,
        force: bool = False,
    ) -> dict:
        """Install subscription roles.

        Route:  POST /api/v2/ansible/subscription-roles
        """
        body: dict[str, Any] = {"roles": roles}
        if global_:
            body["global"] = True
        if force:
            body["force"] = True

        response = self._request(
            "POST", f"{API_BASE}/ansible/subscription-roles", json=body
        )
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def ansible_role_vars(self, roles: list[str]) -> list[dict]:
        """Get variables for roles.

        Route:  POST /api/v2/ansible/role/vars
        """
        response = self._request(
            "POST", f"{API_BASE}/ansible/role/vars", json={"roles": roles}
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for ansible_role_vars",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def ansible_list(self, *, user_id: str | None = None) -> list[dict]:
        """List installed ansible roles/collections.

        Route:  GET /api/v2/ansible
        """
        params: dict[str, Any] = {}
        if user_id is not None:
            params["userID"] = user_id

        response = self._request("GET", f"{API_BASE}/ansible", params=params or None)
        try:
            data = response.json()
        except ValueError as exc:
            raise LudusError(
                "Ludus returned invalid JSON for ansible_list",
                status_code=response.status_code,
            ) from exc
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def ansible_role_scope(
        self,
        roles: list[str],
        *,
        global_: bool = False,
        copy: bool = False,
    ) -> dict:
        """Change the scope of ansible roles.

        Route:  PATCH /api/v2/ansible/role/scope
        """
        body: dict[str, Any] = {"roles": roles}
        if global_:
            body["global"] = True
        if copy:
            body["copy"] = True

        response = self._request("PATCH", f"{API_BASE}/ansible/role/scope", json=body)
        try:
            return response.json()
        except ValueError:
            return {"result": "ok"}

    def ansible_role(
        self,
        role: str,
        action: str,
        *,
        version: str | None = None,
        force: bool = False,
        global_: bool = False,
    ) -> dict:
        """Install/remove/update an ansible role.

        Route:  POST /api/v2/ansible/role
        """
        body: dict[str, Any] = {"role": role, "action": action}
        if version is not None:
            body["version"] = version
        if force:
            body["force"] = True
        if global_:
            body["global"] = True

        response = self._request("POST", f"{API_BASE}/ansible/role", json=body)
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
        """Install an ansible role from a tar file.

        Route:  PUT /api/v2/ansible/role/fromtar
        """
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

    def ansible_collection(
        self,
        collection: str,
        *,
        version: str | None = None,
        force: bool = False,
    ) -> dict:
        """Install an ansible collection.

        Route:  POST /api/v2/ansible/collection
        """
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


def get_ludus_client() -> LudusClient:
    """FastAPI dependency: build a `LudusClient` from app settings.

    The caller is responsible for closing the client (or using it as a
    context manager) — FastAPI's dependency system handles this when
    used with `Depends(get_ludus_client)` via a generator wrapper in the
    routes layer.
    """
    settings = get_settings()
    return LudusClient(
        url=settings.ludus_default_url,
        api_key=settings.ludus_default_api_key,
        verify_tls=settings.ludus_default_verify_tls,
    )
