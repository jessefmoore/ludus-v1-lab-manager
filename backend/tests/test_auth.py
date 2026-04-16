"""Tests for password hashing, JWT session cookie, and admin bootstrap."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.api.auth import router as auth_router
from app.core.config import Settings, get_settings
from app.core.db import Base, get_db
from app.core.security import (
    COOKIE_NAME,
    JWT_ALGORITHM,
    create_access_token,
    hash_password,
)
from app.models.user import User
from app.services.bootstrap import ensure_admin_user

ADMIN_EMAIL = "instructor@example.com"
ADMIN_PASSWORD = "super-secret-test-pw"


@pytest.fixture
def settings() -> Settings:
    """Build a Settings object without hitting a real .env file."""
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email=ADMIN_EMAIL,
        admin_password=ADMIN_PASSWORD,
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="unit-test-api-key",
        _env_file=None,
    )


@pytest.fixture
def db_session() -> Iterator[OrmSession]:
    """Fresh in-memory SQLite DB with Base metadata applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def admin_user(db_session: OrmSession, settings: Settings) -> User:
    """Seed the admin user via the bootstrap helper."""
    return ensure_admin_user(db_session, settings)


@pytest.fixture
def client(
    db_session: OrmSession,
    settings: Settings,
    admin_user: User,
) -> Iterator[TestClient]:
    """FastAPI app exposing only the auth router, wired to the fixture DB."""
    app = FastAPI()
    app.include_router(auth_router)

    def _override_get_db() -> Iterator[OrmSession]:
        yield db_session

    def _override_get_settings() -> Settings:
        return settings

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_settings] = _override_get_settings

    with TestClient(app) as tc:
        yield tc


def test_login_success_sets_cookie_and_returns_user(
    client: TestClient, admin_user: User
) -> None:
    """Correct credentials yield 200, Set-Cookie, and a user payload."""
    resp = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["id"] == admin_user.id
    assert body["user"]["role"] == "instructor"
    assert "password_hash" not in body["user"]
    set_cookie = resp.headers.get("set-cookie", "")
    assert f"{COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie or "httponly" in set_cookie.lower()


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    """Wrong password is rejected with a generic message."""
    resp = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "not-the-right-one"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"
    assert COOKIE_NAME not in resp.headers.get("set-cookie", "")


def test_login_unknown_email_returns_401_same_message(client: TestClient) -> None:
    """Unknown email returns exactly the same error as wrong password."""
    resp = client.post(
        "/api/auth/login",
        json={"email": "noone@example.com", "password": "whatever"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


def test_me_without_cookie_returns_401(client: TestClient) -> None:
    """/me rejects unauthenticated callers."""
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_valid_cookie_returns_user(
    client: TestClient, admin_user: User
) -> None:
    """After login, /me returns the authenticated user."""
    login = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == admin_user.id
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "instructor"
    assert "password_hash" not in body


def test_logout_clears_cookie(client: TestClient) -> None:
    """/logout returns 204 and emits a Set-Cookie that invalidates the session."""
    login = client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200

    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204
    set_cookie = resp.headers.get("set-cookie", "")
    # Expired / cleared cookie: either value is empty, or Max-Age=0, or a past Expires.
    lowered = set_cookie.lower()
    assert COOKIE_NAME in set_cookie
    assert (
        f'{COOKIE_NAME}=""' in set_cookie
        or f"{COOKIE_NAME}=;" in set_cookie
        or "max-age=0" in lowered
        or "expires=" in lowered
    )

    # Subsequent /me call must be unauthenticated.
    after = client.get("/api/auth/me")
    assert after.status_code == 401


def test_expired_token_is_rejected(
    client: TestClient, admin_user: User, settings: Settings
) -> None:
    """A token with a past ``exp`` fails auth on /me."""
    past = datetime.now(UTC) - timedelta(hours=1)
    iat = past - timedelta(hours=2)
    claims = {
        "sub": str(admin_user.id),
        "email": admin_user.email,
        "iat": int(iat.timestamp()),
        "exp": int(past.timestamp()),
    }
    expired = jwt.encode(claims, settings.app_secret_key, algorithm=JWT_ALGORITHM)
    client.cookies.set(COOKIE_NAME, expired)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_ensure_admin_user_is_idempotent(
    db_session: OrmSession, settings: Settings
) -> None:
    """Calling ensure_admin_user twice returns the same row with no duplicates."""
    first = ensure_admin_user(db_session, settings)
    second = ensure_admin_user(db_session, settings)
    assert first.id == second.id
    assert first.email == settings.admin_email
    count = db_session.query(User).count()
    assert count == 1


def test_ensure_admin_user_does_not_overwrite_rotated_password(
    db_session: OrmSession, settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    """If the stored hash was rotated out-of-band, bootstrap leaves it alone."""
    admin = ensure_admin_user(db_session, settings)
    # Simulate a password rotation: replace the stored hash with one that
    # does NOT match settings.admin_password.
    admin.password_hash = hash_password("rotated-password")
    db_session.add(admin)
    db_session.commit()

    rotated_hash = admin.password_hash

    with caplog.at_level("WARNING"):
        again = ensure_admin_user(db_session, settings)

    assert again.id == admin.id
    db_session.refresh(again)
    assert again.password_hash == rotated_hash
    assert any("does not match" in rec.message for rec in caplog.records)


def test_create_access_token_roundtrip_claims(
    admin_user_factory: User, settings: Settings
) -> None:
    """create_access_token produces a JWT that decodes to expected claims."""
    token = create_access_token(admin_user_factory, settings)
    decoded = jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])
    assert decoded["sub"] == str(admin_user_factory.id)
    assert decoded["email"] == admin_user_factory.email
    assert "iat" in decoded
    assert "exp" in decoded
    assert decoded["exp"] > decoded["iat"]


@pytest.fixture
def admin_user_factory(db_session: OrmSession, settings: Settings) -> User:
    """Alias fixture for create_access_token round-trip test."""
    return ensure_admin_user(db_session, settings)
