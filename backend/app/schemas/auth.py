"""Pydantic request/response schemas for the auth endpoints.

Intentionally standalone: this module is imported directly (not via
``app.schemas``) because ``app.schemas.__init__`` is owned by another
slice of the codebase.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    """Credentials submitted to ``POST /api/auth/login``."""

    email: EmailStr
    password: str


class UserRead(BaseModel):
    """Safe, outward-facing view of a ``User`` row. Never includes the hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    created_at: datetime


class LoginResponse(BaseModel):
    """Body returned on a successful login."""

    user: UserRead
