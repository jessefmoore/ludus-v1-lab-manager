"""FastAPI application entry point for insec.ml.

Wires every Phase 1 router into a single app, and uses a lifespan handler
to:

1. Apply database schema (Alembic in production, ``Base.metadata.create_all``
   as a dev/test convenience).
2. Bootstrap the instructor admin user from ``ADMIN_EMAIL`` /
   ``ADMIN_PASSWORD``.

The module is import-safe: constructing the ``FastAPI`` instance does not
touch the database — schema + bootstrap run when the lifespan context
enters (e.g. under ``TestClient(app)`` or uvicorn startup).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.api import (
    auth,
    events,
    invite,
    labs,
    ludus,
    ludus_ansible,
    ludus_groups,
    ludus_testing,
    sessions,
    students,
)
from app.api import settings as settings_api
from app.core.config import Settings, get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.deps import get_db
from app.core.limiter import limiter
from app.middleware.csrf import CSRFMiddleware
from app.middleware.logging import RequestLoggingMiddleware
from app.services.bootstrap import ensure_admin_user

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _apply_schema(settings: Settings) -> None:
    """Bring the database schema up to date.

    * In ``production`` we run ``alembic upgrade head`` programmatically so
      the container starts with exactly the migrations git tracks.
    * In any other environment (``development``, ``testing``, ...) we fall
      back to ``Base.metadata.create_all`` so a freshly-checked-out dev
      box does not need to run alembic out-of-band before the first boot.
    """
    if settings.app_env == "production":
        from alembic.config import Config as AlembicConfig

        from alembic import command as alembic_command

        cfg = AlembicConfig(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        alembic_command.upgrade(cfg, "head")
        logger.info("alembic upgrade head complete")
    else:
        Base.metadata.create_all(engine)
        logger.info(
            "dev fallback: Base.metadata.create_all executed (app_env=%s)",
            settings.app_env,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run migrations + bootstrap the admin user at startup."""
    settings = get_settings()
    _apply_schema(settings)
    with SessionLocal() as db:
        ensure_admin_user(db, settings)
    yield
    # No shutdown work for MVP.


settings = get_settings()

app = FastAPI(
    title="insec.ml",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: deduplicate + filter None/empty before handing to Starlette.
_origins = list({o for o in (settings.public_base_url, "http://localhost:3000") if o})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)

# CSRF: reject cross-origin state-changing requests.
_csrf_host = urlparse(settings.public_base_url).hostname or "localhost"
app.add_middleware(CSRFMiddleware, allowed_host=_csrf_host)

# Every router module already sets its own prefix — include without args.
app.include_router(auth.router)
app.include_router(labs.router)
app.include_router(ludus.router)
app.include_router(ludus_testing.router)
app.include_router(ludus_groups.router)
app.include_router(ludus_ansible.router)
app.include_router(settings_api.router)
app.include_router(sessions.router)
app.include_router(students.router)
app.include_router(events.router)
app.include_router(invite.router)


@app.get("/health")
def health(
    response: Response,
    db: DBSession = Depends(get_db),  # noqa: B008 -- FastAPI idiom
    settings: Settings = Depends(get_settings),  # noqa: B008 -- FastAPI idiom
) -> dict:
    """Health check with DB, storage, and Ludus connectivity."""
    # DB check
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    # Storage check
    storage_ok = Path(settings.config_storage_dir).exists()

    # Ludus check
    ludus_ok = True
    try:
        httpx.get(
            f"{settings.ludus_default_url}/api/status",
            timeout=3.0,
            verify=settings.ludus_default_verify_tls,
        )
    except Exception:
        ludus_ok = False

    healthy = db_ok and storage_ok
    if not healthy:
        response.status_code = 503

    return {
        "status": "ok" if healthy else "degraded",
        "db": db_ok,
        "storage": storage_ok,
        "ludus": ludus_ok,
    }
