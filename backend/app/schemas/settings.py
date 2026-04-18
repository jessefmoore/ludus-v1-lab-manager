"""Pydantic schemas for platform settings endpoints."""

from __future__ import annotations

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


class LudusServersResponse(BaseModel):
    """List of all configured Ludus servers."""

    servers: list[LudusServerInfo]
