"""Password hashing, JWT, and cookie helpers for single-instructor auth.

Security design notes (Phase 1 MVP):

* Sessions are carried as an HS256-signed JWT in an httpOnly cookie
  (``insec_session``) with ``SameSite=Lax`` and ``Secure`` toggled on
  when ``settings.app_env == "production"``.
* CSRF protection is intentionally out of scope for Phase 1. ``SameSite=Lax``
  blocks cross-origin POST/PUT/DELETE from third-party sites on modern
  browsers, which is acceptable for an MVP with a single instructor user
  and a same-origin SPA. This MUST be revisited before shipping anything
  that accepts untrusted cross-site traffic: switch to ``SameSite=Strict``
  and add a CSRF token pattern (double-submit cookie or per-request
  header synchroniser) if/when we open up the UI.
* Passwords are hashed with bcrypt (``passlib``). Plaintext passwords
  are never logged or returned in any response.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Response
from jose import jwt
from passlib.context import CryptContext

from app.core.config import Settings
from app.models.user import User

JWT_ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=12)
COOKIE_NAME = "insec_session"

# ``pwd_context`` is retained for compatibility with the project spec and
# for any future migration scheme wiring (e.g. argon2). The actual hashing
# delegates to the ``bcrypt`` package directly, which avoids a known
# compatibility shim bug in passlib 1.7.4 against bcrypt >= 5.0.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt truncates at 72 bytes; we enforce this limit explicitly rather
# than letting the native library raise, so that long passwords hash
# deterministically (matching typical passlib behaviour).
_BCRYPT_MAX_BYTES = 72


def _encode_password(pw: str) -> bytes:
    encoded = pw.encode("utf-8")
    return encoded[:_BCRYPT_MAX_BYTES]


def hash_password(pw: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    salted = bcrypt.hashpw(_encode_password(pw), bcrypt.gensalt())
    return salted.decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    """Return True iff ``pw`` verifies against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(_encode_password(pw), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash (e.g. a sentinel dummy hash); treat as failed.
        return False


def create_access_token(user: User, settings: Settings) -> str:
    """Build a signed JWT for the given user with a 12h TTL."""
    now = datetime.now(UTC)
    exp = now + TOKEN_TTL
    claims = {
        "sub": str(user.id),
        "email": user.email,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(claims, settings.app_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict:
    """Decode and validate an access token.

    Raises:
        jose.JWTError: on bad signature, malformed token, or expired ``exp``.
    """
    return jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """Attach the session JWT as an httpOnly cookie on the response."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(TOKEN_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=(settings.app_env == "production"),
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    """Expire the session cookie on the client."""
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=(settings.app_env == "production"),
    )
