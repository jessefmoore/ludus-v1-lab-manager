# insec-platform

Training lab deployment management platform for [insec.ml](https://insec.ml).

A self-hosted web platform that wraps [Ludus](https://ludus.cloud) to let instructors
provision, monitor, and tear down student lab environments in bulk for security
trainings and workshops.

## Status

**MVP functional.** Core provisioning, Ludus management, and instructor dashboard are live. See [docs/ROADMAP.md](docs/ROADMAP.md) for roadmap.

## What it does

- Define reusable **lab templates** (Ludus range-config YAML + metadata)
- Create a **training session**: select lab, pick mode (shared/dedicated), add students
- **One-click bulk provision**: creates Ludus users, assigns ranges, generates WireGuard configs
- Share per-student **invite links** — students download their VPN config
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
- **Auth:** Single instructor account, JWT in httpOnly cookie
- **Deployment:** Docker Compose + Caddy reverse proxy

## Project structure

```
insec-platform/
├── backend/
│   ├── app/
│   │   ├── api/                        # FastAPI route handlers
│   │   │   ├── auth.py                 #   login / logout / me
│   │   │   ├── events.py              #   audit log
│   │   │   ├── invite.py              #   public invite + config download
│   │   │   ├── labs.py                #   lab templates CRUD + cover images
│   │   │   ├── ludus.py               #   ranges, snapshots, templates, deploy
│   │   │   ├── ludus_ansible.py       #   Ansible role/collection management
│   │   │   ├── ludus_groups.py        #   Ludus group management
│   │   │   ├── ludus_testing.py       #   testing mode control
│   │   │   ├── sessions.py            #   training sessions CRUD + provision
│   │   │   ├── settings.py            #   platform settings + Ludus servers
│   │   │   └── students.py            #   student CRUD, CSV import, reset
│   │   ├── core/                       # App config and dependency injection
│   │   │   ├── config.py              #   pydantic-settings (env vars)
│   │   │   ├── db.py                  #   SQLAlchemy engine + session factory
│   │   │   ├── deps.py                #   FastAPI dependency injection
│   │   │   ├── limiter.py             #   rate limiting (slowapi)
│   │   │   └── security.py            #   JWT creation + password hashing
│   │   ├── middleware/                 # Request middleware
│   │   │   ├── csrf.py                #   CSRF protection
│   │   │   └── logging.py            #   structured request logging
│   │   ├── models/                     # SQLAlchemy ORM models
│   │   │   ├── event.py               #   audit events
│   │   │   ├── lab_template.py        #   lab templates (range-config YAML)
│   │   │   ├── session.py             #   training sessions
│   │   │   ├── student.py             #   students + invite tokens
│   │   │   └── user.py                #   instructor account
│   │   ├── schemas/                    # Pydantic request/response schemas
│   │   │   ├── auth.py                #   login request/response
│   │   │   ├── common.py              #   shared enums (status, mode)
│   │   │   ├── event.py               #   event read schema
│   │   │   ├── invite.py              #   invite detail schema
│   │   │   ├── lab.py                 #   lab template schemas
│   │   │   ├── ludus.py               #   Ludus API proxy schemas
│   │   │   ├── session.py             #   session create/read/detail
│   │   │   ├── settings.py            #   platform settings schemas
│   │   │   └── student.py             #   student create/read schemas
│   │   ├── services/                   # Business logic (no FastAPI imports)
│   │   │   ├── bootstrap.py           #   admin account seeding on startup
│   │   │   ├── exceptions.py          #   shared Ludus exception types
│   │   │   ├── invite.py              #   invite token + WireGuard config
│   │   │   ├── labs.py                #   lab template CRUD + cover images
│   │   │   ├── ludus.py               #   LudusClient — single Ludus integration
│   │   │   ├── provision.py           #   bulk provisioning orchestrator
│   │   │   ├── sessions.py            #   session lifecycle management
│   │   │   └── students.py            #   student enrollment + reset
│   │   ├── templates/
│   │   │   └── invite.html            #   invite landing page template
│   │   └── main.py                     # FastAPI app factory + startup
│   ├── alembic/                        # DB migrations
│   │   └── versions/
│   │       ├── 0001_initial.py
│   │       └── 0002_add_cover_image_to_lab_templates.py
│   ├── tests/                          # pytest test suite
│   │   ├── conftest.py                #   fixtures, test DB, mock Ludus
│   │   ├── test_app_smoke.py
│   │   ├── test_auth.py
│   │   ├── test_config.py
│   │   ├── test_db.py
│   │   ├── test_events_api.py
│   │   ├── test_invite.py
│   │   ├── test_labs_api.py
│   │   ├── test_ludus_ansible_api.py
│   │   ├── test_ludus_client.py
│   │   ├── test_ludus_discovery_api.py
│   │   ├── test_ludus_groups_api.py
│   │   ├── test_ludus_management_api.py
│   │   ├── test_ludus_testing_api.py
│   │   ├── test_models.py
│   │   ├── test_multi_server.py
│   │   ├── test_provision.py
│   │   ├── test_reset_cooldown.py
│   │   ├── test_schemas.py
│   │   ├── test_sessions_api.py
│   │   ├── test_settings_api.py
│   │   ├── test_students_api.py
│   │   ├── test_students_csv_import.py
│   │   └── test_students_reset.py
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/                        # Typed API client
│   │   │   ├── client.ts              #   HTTP client + endpoint methods
│   │   │   ├── index.ts               #   barrel export
│   │   │   └── types.ts               #   TypeScript interfaces
│   │   ├── components/                 # Reusable UI components
│   │   │   ├── AppLayout.tsx          #   sidebar + main content layout
│   │   │   ├── Button.tsx             #   button variants
│   │   │   ├── Card.tsx               #   card container (stat, gradient)
│   │   │   ├── CommandPalette.tsx     #   Cmd+K search palette
│   │   │   ├── DataTable.tsx          #   sortable/searchable data table
│   │   │   ├── ErrorBoundary.tsx      #   React error boundary
│   │   │   ├── Input.tsx              #   form input
│   │   │   ├── LoadingScreen.tsx      #   full-page loading state
│   │   │   ├── LogViewer.tsx          #   Ludus log viewer
│   │   │   ├── Modal.tsx              #   dialog overlay
│   │   │   ├── PageTransition.tsx     #   animated page transitions
│   │   │   ├── ProtectedRoute.tsx     #   auth route guard
│   │   │   ├── RangeStatePill.tsx     #   Ludus range state indicator
│   │   │   ├── SessionTimeline.tsx    #   session status timeline
│   │   │   ├── Sidebar.tsx            #   navigation sidebar
│   │   │   ├── Skeleton.tsx           #   loading skeleton placeholders
│   │   │   ├── StatusPill.tsx         #   status badge (student/session)
│   │   │   ├── Tabs.tsx               #   tab navigation
│   │   │   ├── Toast.tsx              #   notification toasts
│   │   │   └── TopBar.tsx             #   breadcrumb + actions bar
│   │   ├── contexts/                   # React context providers
│   │   │   ├── AuthContext.tsx        #   authentication state
│   │   │   └── ThemeContext.tsx        #   dark/light theme
│   │   ├── pages/                      # Page-level components
│   │   │   ├── Dashboard.tsx          #   session overview + stats
│   │   │   ├── LabTemplates.tsx       #   lab template management
│   │   │   ├── Login.tsx              #   auth screen
│   │   │   ├── LudusManagement.tsx    #   Ludus server admin (8 tabs)
│   │   │   ├── NotFound.tsx           #   404 page
│   │   │   ├── SessionDetail.tsx      #   session + student management
│   │   │   └── Settings.tsx           #   platform settings
│   │   ├── App.tsx                     # Router + providers
│   │   ├── index.css                   # Tailwind + design system tokens
│   │   ├── main.tsx                    # Entry point
│   │   └── vite-env.d.ts
│   ├── index.html
│   ├── Dockerfile
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── package.json
│   └── package-lock.json
├── docs/
│   ├── ARCHITECTURE.md                 # Data model + provisioning flow
│   ├── ROADMAP.md                      # Phased development plan
│   ├── DESIGN_SYSTEM.md                # Visual design tokens + specs
│   ├── DEPLOY.md                       # Deployment guide
│   ├── AGENTS.md                       # Multi-agent role definitions
│   └── STITCH_PROMPTS.md              # UI prompt archive
├── data/                               # Runtime data (gitignored)
│   ├── configs/                        #   WireGuard .conf files
│   └── uploads/                        #   lab cover images
├── .github/workflows/
│   ├── backend-ci.yml                  # Lint + test + Docker build
│   └── frontend-ci.yml                 # TypeScript check + build
├── docker-compose.yml
├── Caddyfile                           # Reverse proxy config
├── .env.example
├── CHANGELOG.md
└── CLAUDE.md                           # AI assistant instructions
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

Private — all rights reserved (for now).
