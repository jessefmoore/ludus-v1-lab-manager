"""Authentication endpoints: login, logout, current-user introspection."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.deps import get_current_user, get_db
from app.core.security import (
    clear_session_cookie,
    create_access_token,
    hash_password,
    set_session_cookie,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Pre-computed bcrypt hash of a random string. Used on the "no such user"
# branch so that every login request performs the same amount of hashing
# work, masking the existence of an account from a timing side channel.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-mitigation")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
) -> LoginResponse:
    """Verify credentials, set the session cookie, return the user."""
    user = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()

    if user is None:
        # Still do a hash comparison against a throwaway to keep timing
        # between "user exists" and "user does not exist" branches similar.
        verify_password(payload.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(user, settings)
    set_session_cookie(response, token, settings)
    return LoginResponse(user=UserRead.model_validate(user))


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
