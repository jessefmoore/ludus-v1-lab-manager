"""Authentication endpoints: login, logout, current-user introspection."""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user, get_db
from app.core.limiter import limiter
from app.core.security import (
    clear_session_cookie,
    create_access_token,
    hash_password,
    set_session_cookie,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, UserRead
from app.services.ludus_auth import authenticate_ludus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Pre-computed bcrypt hash of a random string. Used on the "no such user"
# branch so that every login request performs the same amount of hashing
# work, masking the existence of an account from a timing side channel.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-mitigation")


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
) -> LoginResponse:
    """Verify credentials, set the session cookie, return the user.

    Rate-limited to 5 requests/minute per IP via slowapi (configured in main.py).
    """
    client_ip = request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "unknown"
    )
    # The submitted identifier may be an app account email/username, a Ludus
    # userID, or a Proxmox username. Try local auth first, then Ludus/Proxmox.
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()

    # 1. Local account (app-managed password).
    if user is not None and verify_password(payload.password, user.password_hash):
        token = create_access_token(user, settings)
        set_session_cookie(response, token, settings)
        return LoginResponse(user=UserRead.model_validate(user))

    # 2. Ludus/Proxmox credentials. On success, just-in-time provision an app
    #    account for that Ludus user (keyed by Ludus userID).
    identity = authenticate_ludus(payload.email, payload.password, settings)
    if identity is not None:
        user = db.execute(
            select(User).where(User.email == identity.user_id)
        ).scalar_one_or_none()
        if user is None:
            user = User(
                email=identity.user_id,
                # Random, unusable local password - this account authenticates
                # via Ludus/Proxmox, not a stored password.
                password_hash=hash_password(secrets.token_urlsafe(32)),
                role="instructor",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("login.ludus provisioned userid=%s ip=%s", identity.user_id, client_ip)
        logger.info("login.ludus success userid=%s ip=%s", identity.user_id, client_ip)
        token = create_access_token(user, settings)
        set_session_cookie(response, token, settings)
        return LoginResponse(user=UserRead.model_validate(user))

    # 3. Both failed. Keep timing consistent when there was no local user.
    if user is None:
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
    logger.warning("login.failed email=%s ip=%s", payload.email, client_ip)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
) -> Response:
    """Clear the session cookie. Idempotent; always 204."""
    clear_session_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def me(
    current_user: User = Depends(get_current_user),  # noqa: B008 -- FastAPI idiom
) -> UserRead:
    """Return the currently authenticated user."""
    return UserRead.model_validate(current_user)
