"""Ludus group management endpoints.

Routes for creating/deleting groups and managing group membership
(users and ranges).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import LudusClientRegistry, get_current_user, get_ludus_client_registry
from app.models.user import User
from app.schemas.ludus import (
    GroupCreateRequest,
    GroupModifyRangesRequest,
    GroupModifyRangesResponse,
    GroupModifyUsersRequest,
    GroupModifyUsersResponse,
    LudusAccessibleRange,
    LudusActionResponse,
    LudusGroup,
    LudusGroupListResponse,
    LudusGroupRangesResponse,
    LudusGroupUser,
    LudusGroupUsersResponse,
)
from app.services.exceptions import LudusError, LudusNotFound
from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ludus/groups", tags=["ludus-groups"])


def _resolve_client(registry: LudusClientRegistry, server: str) -> LudusClient:
    """Resolve a ``LudusClient`` from the registry, raising 400 on unknown server."""
    try:
        return registry.get(server)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("", response_model=LudusGroupListResponse)
def list_groups(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusGroupListResponse:
    """List all groups."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.group_list()
    except LudusError as exc:
        logger.warning("Ludus group_list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    groups = [LudusGroup.model_validate(g) for g in raw]
    return LudusGroupListResponse(groups=groups)


@router.post("", response_model=LudusActionResponse)
def create_group(
    body: GroupCreateRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Create a new group."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.group_create(body.name, description=body.description)
    except LudusError as exc:
        logger.warning("Ludus group_create failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Group created")


@router.delete("/{group_name}", response_model=LudusActionResponse)
def delete_group(
    group_name: str,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Delete a group."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.group_delete(group_name)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus group_delete(%s) failed: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Group deleted")


@router.get("/{group_name}/users", response_model=LudusGroupUsersResponse)
def get_group_users(
    group_name: str,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusGroupUsersResponse:
    """List users in a group."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.group_users(group_name)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus group_users(%s) failed: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    users = [LudusGroupUser.model_validate(u) for u in raw]
    return LudusGroupUsersResponse(users=users)


@router.post("/{group_name}/users", response_model=GroupModifyUsersResponse)
def add_group_users(
    group_name: str,
    body: GroupModifyUsersRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> GroupModifyUsersResponse:
    """Add users to a group."""
    ludus = _resolve_client(registry, server)
    try:
        result = ludus.group_add_users(
            group_name, body.user_ids, managers=body.managers
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus group_add_users(%s) failed: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return GroupModifyUsersResponse.model_validate(result)


@router.delete("/{group_name}/users", response_model=GroupModifyUsersResponse)
def remove_group_users(
    group_name: str,
    body: GroupModifyUsersRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> GroupModifyUsersResponse:
    """Remove users from a group."""
    ludus = _resolve_client(registry, server)
    try:
        result = ludus.group_remove_users(group_name, body.user_ids)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus group_remove_users(%s) failed: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return GroupModifyUsersResponse.model_validate(result)


@router.get("/{group_name}/ranges", response_model=LudusGroupRangesResponse)
def get_group_ranges(
    group_name: str,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusGroupRangesResponse:
    """List ranges assigned to a group."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.group_ranges(group_name)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus group_ranges(%s) failed: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    ranges = [LudusAccessibleRange.model_validate(r) for r in raw]
    return LudusGroupRangesResponse(ranges=ranges)


@router.post("/{group_name}/ranges", response_model=GroupModifyRangesResponse)
def add_group_ranges(
    group_name: str,
    body: GroupModifyRangesRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> GroupModifyRangesResponse:
    """Add ranges to a group."""
    ludus = _resolve_client(registry, server)
    try:
        result = ludus.group_add_ranges(group_name, body.range_ids)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus group_add_ranges(%s) failed: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return GroupModifyRangesResponse.model_validate(result)


@router.delete("/{group_name}/ranges", response_model=GroupModifyRangesResponse)
def remove_group_ranges(
    group_name: str,
    body: GroupModifyRangesRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> GroupModifyRangesResponse:
    """Remove ranges from a group."""
    ludus = _resolve_client(registry, server)
    try:
        result = ludus.group_remove_ranges(group_name, body.range_ids)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Group '{group_name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus group_remove_ranges(%s) failed: %s", group_name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return GroupModifyRangesResponse.model_validate(result)
