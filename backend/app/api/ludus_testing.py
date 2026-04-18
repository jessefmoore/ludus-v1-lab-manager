"""Ludus testing state management endpoints.

Routes for entering/exiting testing mode and managing allowed/denied
domains and IPs during testing.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import LudusClientRegistry, get_current_user, get_ludus_client_registry
from app.models.user import User
from app.schemas.ludus import (
    LudusActionResponse,
    TestingAllowDenyRequest,
    TestingAllowDenyResponse,
    TestingStartRequest,
    TestingStopRequest,
    TestingUpdateRequest,
)
from app.services.exceptions import LudusError, LudusNotFound
from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ludus/testing", tags=["ludus-testing"])


def _resolve_client(registry: LudusClientRegistry, server: str) -> LudusClient:
    """Resolve a ``LudusClient`` from the registry, raising 400 on unknown server."""
    try:
        return registry.get(server)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.put("/start", response_model=LudusActionResponse)
def testing_start(
    body: TestingStartRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Enter testing mode for a range."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.testing_start(range_id=body.range_id, user_id=body.user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus testing_start failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Testing mode started")


@router.put("/stop", response_model=LudusActionResponse)
def testing_stop(
    body: TestingStopRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Exit testing mode for a range."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.testing_stop(
            range_id=body.range_id, user_id=body.user_id, force=body.force
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus testing_stop failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Testing mode stopped")


@router.post("/allow", response_model=TestingAllowDenyResponse)
def testing_allow(
    body: TestingAllowDenyRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> TestingAllowDenyResponse:
    """Allow domains/IPs during testing mode."""
    ludus = _resolve_client(registry, server)
    try:
        result = ludus.testing_allow(
            range_id=body.range_id,
            user_id=body.user_id,
            domains=body.domains,
            ips=body.ips,
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus testing_allow failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return TestingAllowDenyResponse.model_validate(result)


@router.post("/deny", response_model=TestingAllowDenyResponse)
def testing_deny(
    body: TestingAllowDenyRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> TestingAllowDenyResponse:
    """Deny domains/IPs during testing mode."""
    ludus = _resolve_client(registry, server)
    try:
        result = ludus.testing_deny(
            range_id=body.range_id,
            user_id=body.user_id,
            domains=body.domains,
            ips=body.ips,
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus testing_deny failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return TestingAllowDenyResponse.model_validate(result)


@router.post("/update", response_model=LudusActionResponse)
def testing_update(
    body: TestingUpdateRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Update testing configuration."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.testing_update(body.name, range_id=body.range_id, user_id=body.user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus testing_update failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Testing config updated")
