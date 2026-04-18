"""Ludus discovery endpoints: list ranges, fetch range config.

All routes require an authenticated instructor session (cookie-based).
These endpoints proxy to the Ludus API so the frontend can discover
deployed ranges and optionally import their configs as lab templates.
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.deps import LudusClientRegistry, get_current_user, get_ludus_client_registry
from app.models.user import User
from app.schemas.ludus import (
    LudusAccessibleRange,
    LudusAccessibleRangesResponse,
    LudusActionResponse,
    LudusLogEntryDetailResponse,
    LudusLogHistoryEntry,
    LudusLogHistoryResponse,
    LudusRange,
    LudusRangeConfigResponse,
    LudusRangeDetail,
    LudusRangeDetailResponse,
    LudusRangeListResponse,
    LudusRangeLogsResponse,
    LudusRangeTagsResponse,
    LudusRangeUser,
    LudusRangeUsersResponse,
    LudusSnapshot,
    LudusSnapshotListResponse,
    LudusTemplate,
    LudusTemplateListResponse,
    LudusTextResponse,
    LudusUser,
    LudusUserListResponse,
    PowerActionRequest,
    RangeAbortRequest,
    RangeCreateRequest,
    RangeRevokeRequest,
    SnapshotCreateRequest,
    SnapshotRevertRequest,
    UserCreateRequest,
    UserCreateResponse,
)
from app.services.exceptions import LudusError, LudusNotFound, LudusUserExists
from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ludus", tags=["ludus"])


def _resolve_client(registry: LudusClientRegistry, server: str) -> LudusClient:
    """Resolve a ``LudusClient`` from the registry, raising 400 on unknown server."""
    try:
        return registry.get(server)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/ranges", response_model=LudusRangeListResponse)
def list_ranges(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusRangeListResponse:
    """List all ranges visible on the Ludus instance."""
    ludus = _resolve_client(registry, server)
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
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusRangeConfigResponse:
    """Fetch the range-config YAML for a range by its number."""
    ludus = _resolve_client(registry, server)
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
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusUserListResponse:
    """List all users on the Ludus instance."""
    ludus = _resolve_client(registry, server)
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


@router.post("/users", response_model=UserCreateResponse)
def create_user(
    body: UserCreateRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> UserCreateResponse:
    """Create a new user on the Ludus instance."""
    ludus = _resolve_client(registry, server)
    try:
        data = ludus.user_add(body.user_id, body.name, body.email)
    except LudusUserExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User '{body.user_id}' already exists",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus user_add(%s) failed: %s", body.user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return UserCreateResponse.model_validate(data)


@router.delete("/users/{user_id}", response_model=LudusActionResponse)
def delete_user(
    user_id: str,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Delete a user from the Ludus instance."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.user_rm(user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus user_rm(%s) failed: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="User deleted")


@router.get("/users/{user_id}/wireguard")
def get_user_wireguard(
    user_id: str,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> StreamingResponse:
    """Download a user's WireGuard config file."""
    ludus = _resolve_client(registry, server)
    try:
        config_text = ludus.user_wireguard(user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus user_wireguard(%s) failed: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return StreamingResponse(
        io.BytesIO(config_text.encode()),
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename={user_id}.conf"},
    )


@router.post("/ranges/{range_number}/deploy", response_model=LudusActionResponse)
def deploy_range(
    range_number: int,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Deploy an already-configured range by its number."""
    ludus = _resolve_client(registry, server)
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
    server: str = "default",
    force: bool = False,
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Destroy a range by its number."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.range_destroy(range_number, force=force)
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


# -- Power management -------------------------------------------------------


@router.post("/ranges/{range_number}/power-on", response_model=LudusActionResponse)
def power_on_range(
    range_number: int,
    body: PowerActionRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Power on VMs in a range."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.range_power_on(body.user_id, machines=body.machines)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Range or user not found for range {range_number}",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_power_on(range=%d) failed: %s", range_number, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Power on initiated")


@router.post("/ranges/{range_number}/power-off", response_model=LudusActionResponse)
def power_off_range(
    range_number: int,
    body: PowerActionRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Power off VMs in a range."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.range_power_off(body.user_id, machines=body.machines)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Range or user not found for range {range_number}",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_power_off(range=%d) failed: %s", range_number, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Power off initiated")


# -- Snapshot management -----------------------------------------------------


@router.get("/snapshots", response_model=LudusSnapshotListResponse)
def list_snapshots(
    user_id: str | None = None,
    range_number: int | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusSnapshotListResponse:
    """List snapshots, optionally filtered by user or range."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.snapshot_list(user_id=user_id, range_number=range_number)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User or range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus snapshot_list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    # Ludus returns [{"snapshots": [{name, vmid, vmname, ...}, ...]}].
    # Flatten the per-VM entries and deduplicate by snapshot name.
    flat: list[dict] = []
    for item in raw:
        if isinstance(item, dict) and "snapshots" in item:
            flat.extend(item["snapshots"])
        else:
            flat.append(item)

    by_name: dict[str, dict] = {}
    for entry in flat:
        name = entry.get("name", "")
        if name not in by_name:
            by_name[name] = {
                "name": name,
                "description": entry.get("description"),
                "vmids": [],
            }
        vmid = entry.get("vmid")
        if vmid is not None:
            by_name[name]["vmids"].append(vmid)

    snapshots = [LudusSnapshot.model_validate(s) for s in by_name.values()]
    return LudusSnapshotListResponse(snapshots=snapshots)


@router.post("/snapshots", response_model=LudusActionResponse)
def create_snapshot(
    body: SnapshotCreateRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Create a new snapshot."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.snapshot_create(
            body.user_id,
            body.name,
            description=body.description,
            include_ram=body.include_ram,
            vmids=body.vmids,
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus snapshot_create failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Snapshot creation started")


@router.post("/snapshots/revert", response_model=LudusActionResponse)
def revert_snapshot(
    body: SnapshotRevertRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Revert to a named snapshot."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.snapshot_revert(body.user_id, body.name, vmids=body.vmids)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot or user not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus snapshot_revert failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Snapshot revert started")


@router.delete("/snapshots/{name}", response_model=LudusActionResponse)
def delete_snapshot(
    name: str,
    user_id: str,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Delete a snapshot by name."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.snapshot_delete(user_id, name)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot '{name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus snapshot_delete(%s) failed: %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Snapshot deleted")


# -- Template management ----------------------------------------------------


@router.get("/templates", response_model=LudusTemplateListResponse)
def list_templates(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusTemplateListResponse:
    """List all available VM templates."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.template_list()
    except LudusError as exc:
        logger.warning("Ludus template_list failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    templates = [LudusTemplate.model_validate(t) for t in raw]
    return LudusTemplateListResponse(templates=templates)


@router.delete("/templates/{name}", response_model=LudusActionResponse)
def delete_template(
    name: str,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Delete a VM template by name."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.template_delete(name)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{name}' not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus template_delete(%s) failed: %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Template deleted")


# -- Range detail / VM operations -------------------------------------------


@router.get("/range/vms", response_model=LudusRangeDetailResponse)
def get_range_vms(
    range_id: int | None = None,
    user_id: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusRangeDetailResponse:
    """Get VMs for a range with power/testing state."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.range_get_vms(range_id=range_id, user_id=user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_get_vms failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    ranges = [LudusRangeDetail.model_validate(r) for r in raw]
    return LudusRangeDetailResponse(ranges=ranges)


@router.delete("/vm/{vm_id}", response_model=LudusActionResponse)
def destroy_vm(
    vm_id: int,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Destroy a single VM."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.vm_destroy(vm_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VM {vm_id} not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus vm_destroy(%d) failed: %s", vm_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="VM destroyed")


@router.post("/range/abort", response_model=LudusActionResponse)
def abort_range(
    body: RangeAbortRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Abort a running range deployment."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.range_abort(range_id=body.range_id, user_id=body.user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_abort failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Abort initiated")


@router.delete("/range/{range_id}/vms", response_model=LudusActionResponse)
def delete_range_vms(
    range_id: int,
    user_id: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Delete all VMs in a range."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.range_delete_vms(range_id, user_id=user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Range {range_id} not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_delete_vms(%d) failed: %s", range_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="VMs deleted")


@router.get("/range/tags", response_model=LudusRangeTagsResponse)
def get_range_tags(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusRangeTagsResponse:
    """List all range tags."""
    ludus = _resolve_client(registry, server)
    try:
        tags = ludus.range_tags()
    except LudusError as exc:
        logger.warning("Ludus range_tags failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusRangeTagsResponse(tags=tags)


@router.get("/range/config/example", response_model=LudusTextResponse)
def get_range_config_example(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusTextResponse:
    """Get an example range config YAML."""
    ludus = _resolve_client(registry, server)
    try:
        content = ludus.range_config_example()
    except LudusError as exc:
        logger.warning("Ludus range_config_example failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusTextResponse(content=content)


@router.get("/range/logs", response_model=LudusRangeLogsResponse)
def get_range_logs(
    range_id: int | None = None,
    user_id: str | None = None,
    tail: int | None = None,
    cursor: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusRangeLogsResponse:
    """Get deployment logs for a range."""
    ludus = _resolve_client(registry, server)
    try:
        data = ludus.range_logs(
            range_id=range_id, user_id=user_id, tail=tail, cursor=cursor
        )
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_logs failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusRangeLogsResponse.model_validate(data)


@router.get("/range/logs/history", response_model=LudusLogHistoryResponse)
def get_range_logs_history(
    range_id: int | None = None,
    user_id: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusLogHistoryResponse:
    """Get deployment log history."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.range_logs_history(range_id=range_id, user_id=user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_logs_history failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    entries = [LudusLogHistoryEntry.model_validate(e) for e in raw]
    return LudusLogHistoryResponse(entries=entries)


@router.get("/range/logs/history/{log_id}", response_model=LudusLogEntryDetailResponse)
def get_range_log_entry(
    log_id: int,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusLogEntryDetailResponse:
    """Get a specific deployment log entry."""
    ludus = _resolve_client(registry, server)
    try:
        data = ludus.range_log_entry(log_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log entry {log_id} not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_log_entry(%d) failed: %s", log_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusLogEntryDetailResponse.model_validate(data)


@router.get("/range/etchosts", response_model=LudusTextResponse)
def get_range_etchosts(
    range_id: int | None = None,
    user_id: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusTextResponse:
    """Get /etc/hosts content for a range."""
    ludus = _resolve_client(registry, server)
    try:
        content = ludus.range_etchosts(range_id=range_id, user_id=user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_etchosts failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusTextResponse(content=content)


@router.get("/range/sshconfig", response_model=LudusTextResponse)
def get_range_sshconfig(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusTextResponse:
    """Get SSH config for the range."""
    ludus = _resolve_client(registry, server)
    try:
        content = ludus.range_sshconfig()
    except LudusError as exc:
        logger.warning("Ludus range_sshconfig failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusTextResponse(content=content)


@router.get("/range/rdpconfigs")
def get_range_rdpconfigs(
    range_id: int | None = None,
    user_id: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> StreamingResponse:
    """Get RDP configs as a zip file."""
    ludus = _resolve_client(registry, server)
    try:
        content = ludus.range_rdpconfigs(range_id=range_id, user_id=user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_rdpconfigs failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=rdpconfigs.zip"},
    )


@router.get("/range/ansibleinventory", response_model=LudusTextResponse)
def get_range_ansibleinventory(
    range_id: int | None = None,
    user_id: str | None = None,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusTextResponse:
    """Get Ansible inventory YAML for a range."""
    ludus = _resolve_client(registry, server)
    try:
        content = ludus.range_ansibleinventory(range_id=range_id, user_id=user_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_ansibleinventory failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusTextResponse(content=content)


@router.post("/ranges/create", response_model=LudusActionResponse)
def create_range(
    body: RangeCreateRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Create a new range."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.range_create(body.name, body.range_id)
    except LudusError as exc:
        logger.warning("Ludus range_create failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Range created")


@router.delete("/ranges/revoke", response_model=LudusActionResponse)
def revoke_range(
    body: RangeRevokeRequest,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusActionResponse:
    """Revoke a user's access to a range."""
    ludus = _resolve_client(registry, server)
    try:
        ludus.range_revoke(body.user_id, body.range_id, force=body.force)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User or range not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_revoke failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    return LudusActionResponse(status="ok", detail="Range access revoked")


@router.get("/ranges/{range_id}/users", response_model=LudusRangeUsersResponse)
def get_range_users(
    range_id: int,
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusRangeUsersResponse:
    """List users with access to a range."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.range_users(range_id)
    except LudusNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Range {range_id} not found",
        ) from exc
    except LudusError as exc:
        logger.warning("Ludus range_users(%d) failed: %s", range_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    users = [LudusRangeUser.model_validate(u) for u in raw]
    return LudusRangeUsersResponse(users=users)


@router.get("/ranges/accessible", response_model=LudusAccessibleRangesResponse)
def get_accessible_ranges(
    server: str = "default",
    _: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
    registry: LudusClientRegistry = Depends(get_ludus_client_registry),  # noqa: B008
) -> LudusAccessibleRangesResponse:
    """List ranges accessible to the current user."""
    ludus = _resolve_client(registry, server)
    try:
        raw = ludus.ranges_accessible()
    except LudusError as exc:
        logger.warning("Ludus ranges_accessible failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Ludus error: {exc}",
        ) from exc

    ranges = [LudusAccessibleRange.model_validate(r) for r in raw]
    return LudusAccessibleRangesResponse(ranges=ranges)
