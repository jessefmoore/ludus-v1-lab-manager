"""Request logging middleware with correlation IDs."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("insec.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log method, path, status, and duration for every request.

    Generates an ``X-Request-ID`` header (uuid4) attached to the response
    for correlation. Skips ``/health`` to reduce noise.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        duration_ms = (time.monotonic() - start) * 1000

        if request.url.path != "/health":
            logger.info(
                "%s %s %d %.1fms request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )

        return response
