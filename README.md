# ludus-helm

Training lab deployment management platform powered by [Ludus](https://ludus.cloud).

<img width="1343" height="752" alt="image" src="https://github.com/user-attachments/assets/91784d84-2a3c-4264-8b1d-d9c812be445a" />

A self-hosted web platform that wraps [Ludus](https://ludus.cloud) to let instructors
provision, monitor, and tear down student lab environments in bulk for security
trainings and workshops.

## Status

**MVP functional.** Core provisioning, Ludus management, and instructor dashboard are live. See [docs/ROADMAP.md](docs/ROADMAP.md) for roadmap.

## What it does

- Define reusable **lab templates** (Ludus range-config YAML + metadata)
- Create a **training session**: select lab, pick mode (shared/dedicated), add students
- **One-click bulk provision**: creates Ludus users, assigns ranges, generates WireGuard configs
- Share per-student **invite links** - students download their VPN config
- **Live dashboard**: student status, range health, snapshot state
- Per-student **lab reset** (triggers Ludus snapshot revert)
- **One-click teardown**: cleanup all Ludus users, configs, and artifacts
- Full **Ludus management UI**: ranges, snapshots, users, groups, testing mode, Ansible roles

## Architecture

```
┌─────────────────────────────┐
│  React UI (Stitch design)   │
│  Instructor dashboard       │
└──────────────┬──────────────┘
               │ REST / JSON
               ▼
┌─────────────────────────────┐
│  FastAPI backend             │
│  - sessions / students       │
│  - ludus wrapper             │
│  - invites                   │
└──────┬──────────────┬────────┘
       │              │
       ▼              ▼
  [Postgres]     [Ludus API]
                 (one or more servers)
```

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic 2, httpx
- **Frontend:** React 18 + TypeScript + Vite + Tailwind CSS
- **DB:** PostgreSQL (via Docker Compose)
- **Auth:** Single instructor account, JWT
- **Deployment:** Docker Compose + Caddy reverse proxy

## Project structure

```
ludus-helm/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   ├── core/             # Config, DB, auth, dependency injection
│   │   ├── middleware/       # CSRF, request logging
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── services/         # Business logic + LudusClient
│   │   └── main.py
│   ├── alembic/              # DB migrations
│   └── tests/                # pytest suite (24 test files)
├── frontend/
│   ├── src/
│   │   ├── api/              # Typed HTTP client
│   │   ├── components/       # Reusable UI (17 components)
│   │   ├── contexts/         # Auth + theme providers
│   │   └── pages/            # Dashboard, Sessions, Labs, Ludus, Settings
│   └── vite.config.ts
├── docs/                     # Architecture, roadmap, design system
├── docker-compose.yml
├── Caddyfile                 # Reverse proxy
└── .github/workflows/        # CI (backend lint+test, frontend build)
```

## Quick start

```bash
cp .env.example .env
# edit .env: set ADMIN_PASSWORD, APP_SECRET_KEY, LUDUS_DEFAULT_API_KEY
docker compose up -d
# UI at http://localhost (Caddy), API at http://localhost/api
```

### Local development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pytest                    # full suite
pytest -xvs tests/test_students_api.py   # single file, verbose
```

## License

[MIT](LICENSE)
