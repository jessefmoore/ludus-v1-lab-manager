"""Platform settings endpoints: view config, test Ludus, change password.

All routes require an authenticated instructor session (cookie-based).
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import (
    LudusClientRegistry,
    get_current_user,
    get_db,
    get_ludus_client_registry,
)
from app.core.security import hash_password, verify_password
from app.models.event import Event
from app.models.user import User
from app.schemas.settings import (
    ChangePasswordRequest,
    LudusServerInfo,
    LudusServersResponse,
    LudusTestResponse,
    PlatformSettingsResponse,
)
from app.services.exceptions import LudusError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _mask_key(key: str) -> str:
    """Mask an API key, showing only the last 4 characters."""
    if len(key) <= 4:
        return "****"
    return f"****...{key[-4:]}"


@router.get("", response_model=PlatformSettingsResponse)
def get_settings_view(
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> PlatformSettingsResponse:
    """Return platform configuration with masked secrets."""
    return PlatformSettingsResponse(
        ludus_server_url=settings.ludus_default_url,
        ludus_api_key_masked=_mask_key(settings.ludus_default_api_key),
        ludus_verify_tls=settings.ludus_default_verify_tls,
        admin_email=settings.admin_email,
        invite_token_ttl_hours=settings.invite_token_ttl_hours,
        public_base_url=settings.public_base_url,
    )


@router.get("/ludus-servers", response_model=LudusServersResponse)
def list_ludus_servers(
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusServersResponse:
    """Return all configured Ludus servers with masked API keys."""
    servers = [
        LudusServerInfo(
            name=cfg.name,
            url=cfg.url,
            api_key_masked=_mask_key(cfg.api_key),
            verify_tls=cfg.verify_tls,
        )
        for cfg in registry.servers.values()
    ]
    return LudusServersResponse(servers=servers)


@router.post("/test-ludus", response_model=LudusTestResponse)
def test_ludus_connection(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusTestResponse:
    """Test connectivity to a Ludus server by listing ranges."""
    try:
        client = registry.get(server)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        t0 = time.monotonic()
        client.range_list()
        latency_ms = int((time.monotonic() - t0) * 1000)
    except LudusError as exc:
        logger.warning("Ludus connectivity test failed (server=%s): %s", server, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusTestResponse(status="ok", latency_ms=latency_ms)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
) -> Response:
    """Change the authenticated user's password."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    user.password_hash = hash_password(payload.new_password)

    event = Event(
        session_id=None,
        student_id=None,
        action="admin.password_changed",
        details_json={"user_id": user.id},
    )
    db.add(event)
    db.commit()

    logger.info("admin.password_changed user_id=%s", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
