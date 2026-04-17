"""Ludus discovery endpoints: list ranges, fetch range config.

All routes require an authenticated instructor session (cookie-based).
These endpoints proxy to the Ludus API so the frontend can discover
deployed ranges and optionally import their configs as lab templates.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import get_current_user, get_ludus_client
from app.models.user import User
from app.schemas.ludus import (
    LudusActionResponse,
    LudusRange,
    LudusRangeConfigResponse,
    LudusRangeListResponse,
    LudusUser,
    LudusUserListResponse,
)
from app.services.exceptions import LudusError, LudusNotFound
from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ludus", tags=["ludus"])


@router.get("/ranges", response_model=LudusRangeListResponse)
def list_ranges(
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    ludus: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
) -> LudusRangeListResponse:
    """List all ranges visible on the Ludus instance."""
    try:
        raw = ludus.range_list()
    except LudusError as exc:
        logger.warning("Ludus range_list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    ranges = [LudusRange.model_validate(r) for r in raw]
    return LudusRangeListResponse(ranges=ranges)


@router.get("/ranges/{range_number}/config", response_model=LudusRangeConfigResponse)
def get_range_config(
    range_number: int,
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    ludus: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
) -> LudusRangeConfigResponse:
    """Fetch the range-config YAML for a range by its number."""
    try:
        config_yaml = ludus.range_get_config(range_number=range_number)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Range config not found for range {range_number}",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_get_config(range_number=%d) failed: %s", range_number, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusRangeConfigResponse(range_number=range_number, config_yaml=config_yaml)


@router.get("/users", response_model=LudusUserListResponse)
def list_users(
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    ludus: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
) -> LudusUserListResponse:
    """List all users on the Ludus instance."""
    try:
        raw = ludus.user_list()
    except LudusError as exc:
        logger.warning("Ludus user_list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    users = [LudusUser.model_validate(u) for u in raw]
    return LudusUserListResponse(users=users)


@router.post("/ranges/{range_number}/deploy", response_model=LudusActionResponse)
def deploy_range(
    range_number: int,
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    ludus: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
) -> LudusActionResponse:
    """Deploy an already-configured range by its number."""
    try:
        ludus.range_deploy_existing(range_number=range_number)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Range {range_number} not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_deploy_existing(range_number=%d) failed: %s", range_number, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Deployment started")


@router.delete("/ranges/{range_number}", response_model=LudusActionResponse)
def destroy_range(
    range_number: int,
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    ludus: LudusClient = Depends(get_ludus_client),  # noqa: B008 -- FastAPI idiom
) -> LudusActionResponse:
    """Destroy a range by its number."""
    try:
        ludus.range_destroy(range_number)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Range {range_number} not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_destroy(range_number=%d) failed: %s", range_number, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Range destroyed")
