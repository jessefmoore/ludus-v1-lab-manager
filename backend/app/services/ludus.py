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
    POST   /api/v2/ranges/assign/{userID}/{rangeID}       -> range_assign
    GET    /api/v2/user/wireguard?userID=<userID>         -> user_wireguard
           returns JSON {"result": {"wireGuardConfig": "<.conf text>"}}
    POST   /api/v2/snapshots/rollback?userID=<userID>     -> snapshot_revert
           body: {"name": "<snapshot>"}
    PUT    /api/v2/range/config?userID=<userID>           -> range_deploy (step 1)
           multipart form: file=<range-config.yml>, force=true
    POST   /api/v2/range/deploy?userID=<userID>           -> range_deploy (step 2)
           body: {"force": false}
    GET    /api/v2/range/all                              -> range_list
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

    def snapshot_revert(self, userid: str, name: str) -> None:
        """Revert the user's range to a named snapshot.

        Route:  POST /api/v2/snapshots/rollback?userID=<userID>
        Body:   {"name": "<snapshot_name>"}
        Raises:
            LudusAuthError on 401/403.
            LudusNotFound on 404 (snapshot or range missing).
            LudusError on any other non-2xx.
        """
        self._request(
            "POST",
            f"{API_BASE}/snapshots/rollback",
            params={"userID": userid},
            json={"name": name},
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
