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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, invite, labs, sessions, students
from app.core.config import Settings, get_settings
from app.core.db import Base, SessionLocal, engine
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

        cfg = AlembicConfig(
            str(Path(__file__).resolve().parent.parent / "alembic.ini")
        )
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

# CORS: deduplicate + filter None/empty before handing to Starlette.
_origins = list({o for o in (settings.public_base_url, "http://localhost:3000") if o})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every router module already sets its own prefix — include without args.
app.include_router(auth.router)
app.include_router(labs.router)
app.include_router(sessions.router)
app.include_router(students.router)
app.include_router(invite.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
