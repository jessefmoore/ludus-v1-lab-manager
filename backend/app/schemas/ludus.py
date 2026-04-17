"""Pydantic schemas for Ludus discovery endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LudusRange(BaseModel):
    """A single range reported by Ludus.

    Only ``rangeID`` and ``rangeNumber`` are guaranteed by every Ludus
    version; the rest are optional and may vary. ``extra="allow"`` keeps
    us forward-compatible with new fields Ludus might add.

    Field names match the camelCase keys returned by the Ludus API.
    """

    model_config = ConfigDict(extra="allow")

    rangeID: str  # noqa: N815 — matches Ludus JSON key
    rangeNumber: int  # noqa: N815 — matches Ludus JSON key
    name: str | None = None
    numberOfVMs: int | None = None  # noqa: N815 — matches Ludus JSON key
    rangeState: str | None = None  # noqa: N815 — matches Ludus JSON key
    lastDeployment: str | None = None  # noqa: N815 — matches Ludus JSON key
    description: str | None = None
    testingEnabled: bool | None = None  # noqa: N815 — matches Ludus JSON key


class LudusRangeListResponse(BaseModel):
    """Wrapper returned by ``GET /api/ludus/ranges``."""

    ranges: list[LudusRange]


class LudusRangeConfigResponse(BaseModel):
    """Wrapper returned by ``GET /api/ludus/ranges/{range_number}/config``."""

    range_number: int
    config_yaml: str


class LudusUser(BaseModel):
    """A single user reported by Ludus.

    Field names match the camelCase keys returned by the Ludus API.
    ``extra="allow"`` keeps us forward-compatible with new fields.
    """

    model_config = ConfigDict(extra="allow")

    userID: str  # noqa: N815 — matches Ludus JSON key
    name: str | None = None
    dateCreated: str | None = None  # noqa: N815 — matches Ludus JSON key
    proxmoxUsername: str | None = None  # noqa: N815 — matches Ludus JSON key


class LudusUserListResponse(BaseModel):
    """Wrapper returned by ``GET /api/ludus/users``."""

    users: list[LudusUser]


class LudusActionResponse(BaseModel):
    """Generic success response for Ludus management actions."""

    status: str
    detail: str | None = None
