"""Pydantic schemas for platform settings endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlatformSettingsResponse(BaseModel):
    """Read-only view of platform configuration (API key is masked)."""

    ludus_server_url: str
    ludus_api_key_masked: str
    ludus_verify_tls: bool
    admin_email: str
    invite_token_ttl_hours: int
    public_base_url: str


class ChangePasswordRequest(BaseModel):
    """Payload for the change-password endpoint."""

    current_password: str
    new_password: str = Field(min_length=8)


class LudusTestResponse(BaseModel):
    """Result of a Ludus connectivity test."""

    status: str
    latency_ms: int


class LudusServerInfo(BaseModel):
    """Info about a single configured Ludus server (API key masked)."""

    name: str
    url: str
    api_key_masked: str
    verify_tls: bool
    source: Literal["env", "db"] = "env"
    # Manually-configured physical host capacity (None = unset).
    cpu_capacity: int | None = None
    ram_capacity_gb: int | None = None


class LudusServersResponse(BaseModel):
    """List of all configured Ludus servers."""

    servers: list[LudusServerInfo]


class LudusServerCreate(BaseModel):
    """Payload for creating a new DB-managed Ludus server."""

    name: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=64)
    url: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    verify_tls: bool = False
    cpu_capacity: int | None = Field(default=None, ge=1)
    ram_capacity_gb: int | None = Field(default=None, ge=1)


class LudusServerUpdate(BaseModel):
    """Payload for updating a DB-managed Ludus server (all optional)."""

    url: str | None = None
    api_key: str | None = None
    verify_tls: bool | None = None
    cpu_capacity: int | None = Field(default=None, ge=1)
    ram_capacity_gb: int | None = Field(default=None, ge=1)
