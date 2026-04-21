# syntax=docker/dockerfile:1.6
#
# ludus-helm backend image (multi-stage).
#
# Note on migrations:
#   The FastAPI lifespan handler in app/main.py calls `_apply_schema()`, which
#   runs `alembic upgrade head` programmatically whenever APP_ENV=production.
#   That means this container does NOT need an entrypoint.sh that invokes
#   alembic before uvicorn - doing so would duplicate work and risk a race.
#   We rely on lifespan + direct CMD uvicorn.

# ---------- Stage 1: builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for bcrypt / cryptography wheels in case pre-built wheels are
# unavailable on the target arch. Stripped from final image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install production dependencies first so this layer caches on code-only changes.
COPY backend/pyproject.toml /app/pyproject.toml

# Need the package tree present for `pip install .` (PEP 621 + setuptools).
COPY backend/app /app/app
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/alembic.ini

RUN pip install --prefix=/install .

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/usr/local/bin:${PATH}"

# Non-root runtime user. Use fixed UID/GID 1000 so bind-mounted host dirs
# (e.g. ./data) owned by the typical developer uid are writable without a
# host-side chown dance. Override with build args if your host uses a
# different uid.
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd -g "${APP_GID}" app \
 && useradd -u "${APP_UID}" -g "${APP_GID}" -M -s /sbin/nologin -d /app app

WORKDIR /app

# Pull site-packages + console scripts (uvicorn, alembic) from builder.
COPY --from=builder /install /usr/local

# Application code.
COPY --from=builder /app/app /app/app
COPY --from=builder /app/alembic /app/alembic
COPY --from=builder /app/alembic.ini /app/alembic.ini

# Data dir is a mount point at runtime; pre-create so the non-root user can
# write to it even if the host bind-mount lands with loose perms.
RUN mkdir -p /app/data \
 && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
