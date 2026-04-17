"""CSRF protection via Origin/Referer header validation.

Lightweight approach: for state-changing methods (POST/PUT/PATCH/DELETE),
reject requests where the Origin or Referer header doesn't match the
configured ``PUBLIC_BASE_URL`` host. No token-based CSRF needed since we
control the frontend.

Skips:
- ``/api/auth/login`` — no existing session to abuse.
- ``/invite/`` — public endpoints, no auth.
- Safe methods (GET, HEAD, OPTIONS).
"""

import logging
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_STATE_CHANGING = {"POST", "PUT", "PATCH", "DELETE"}
_SKIP_PATHS = {"/api/auth/login"}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin state-changing requests."""

    def __init__(self, app, allowed_host: str) -> None:
        super().__init__(app)
        self.allowed_host = allowed_host

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in _STATE_CHANGING:
            return await call_next(request)

        path = request.url.path
        if path in _SKIP_PATHS or path.startswith("/invite/"):
            return await call_next(request)

        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            parsed = urlparse(origin)
            request_host = parsed.hostname or ""
            if request_host != self.allowed_host:
                logger.warning(
                    "csrf.rejected method=%s path=%s origin=%s",
                    request.method,
                    path,
                    origin,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-origin request rejected"},
                )

        return await call_next(request)
