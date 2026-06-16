"""Ludus Ansible management endpoints.

Routes for managing Ansible roles, collections, and subscriptions
on the Ludus server.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.deps import LudusClientRegistry, get_current_user, get_ludus_client_registry
from app.models.user import User
from app.schemas.ludus import (
    AnsibleCollectionRequest,
    AnsibleInstallSubRolesRequest,
    AnsibleRoleActionRequest,
    AnsibleRoleScopeRequest,
    AnsibleRoleVarsRequest,
    LudusActionResponse,
    LudusInstalledRole,
    LudusInstalledRolesResponse,
    LudusRoleVar,
    LudusRoleVarsResponse,
    LudusSubscriptionRole,
    LudusSubscriptionRolesResponse,
)
from app.services.exceptions import LudusError, LudusNotFound
from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ludus/ansible", tags=["ludus-ansible"])


def _resolve_client(registry: LudusClientRegistry, server: str) -> LudusClient:
    """Resolve a ``LudusClient`` from the registry, raising 400 on unknown server."""
    try:
        return registry.get(server)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/subscription-roles", response_model=LudusSubscriptionRolesResponse)
def list_subscription_roles(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusSubscriptionRolesResponse:
    """List available subscription roles."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.ansible_subscription_roles()
    except LudusError as exc:
        logger.warning("Ludus ansible_subscription_roles failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    roles = [LudusSubscriptionRole.model_validate(r) for r in raw]
    return LudusSubscriptionRolesResponse(roles=roles)


@router.post("/subscription-roles", response_model=LudusActionResponse)
def install_subscription_roles(
    body: AnsibleInstallSubRolesRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Install subscription roles."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.ansible_install_subscription_roles(
            body.roles, global_=body.global_, force=body.force
        )
    except LudusError as exc:
        logger.warning("Ludus ansible_install_subscription_roles failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Subscription roles installed")


@router.post("/role/vars", response_model=LudusRoleVarsResponse)
def get_role_vars(
    body: AnsibleRoleVarsRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusRoleVarsResponse:
    """Get variables for roles."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.ansible_role_vars(body.roles)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus ansible_role_vars failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    vars_ = [LudusRoleVar.model_validate(v) for v in raw]
    return LudusRoleVarsResponse(vars=vars_)


@router.get("", response_model=LudusInstalledRolesResponse)
def list_installed(
    user_id: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusInstalledRolesResponse:
    """List installed ansible roles and collections."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.ansible_list(user_id=user_id)
    except LudusError as exc:
        logger.warning("Ludus ansible_list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    roles = [LudusInstalledRole.model_validate(r) for r in raw]
    return LudusInstalledRolesResponse(roles=roles)


@router.patch("/role/scope", response_model=LudusActionResponse)
def change_role_scope(
    body: AnsibleRoleScopeRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Change the scope of ansible roles."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.ansible_role_scope(body.roles, global_=body.global_, copy=body.copy_roles)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus ansible_role_scope failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Role scope updated")


@router.post("/role", response_model=LudusActionResponse)
def manage_role(
    body: AnsibleRoleActionRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Install, remove, or update an ansible role."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.ansible_role(
            body.role,
            body.action,
            version=body.version,
            force=body.force,
            global_=body.global_,
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus ansible_role failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail=f"Role {body.action} completed")


@router.put("/role/fromtar", response_model=LudusActionResponse)
def install_role_from_tar(
    file: UploadFile = File(...),  # noqa: B008 -- FastAPI idiom
    force: bool = False,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Install an ansible role from a tar file."""
    ludus = _resolve_client(registry, server)
    try:
        file_data = file.file.read()
        ludus.ansible_role_from_tar(
            file_data, file.filename or "role.tar.gz", force=force
        )
    except LudusError as exc:
        logger.warning("Ludus ansible_role_from_tar failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Role installed from tar")


@router.post("/collection", response_model=LudusActionResponse)
def install_collection(
    body: AnsibleCollectionRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Install an ansible collection."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.ansible_collection(
            body.collection, version=body.version, force=body.force
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus ansible_collection failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Collection installed")
