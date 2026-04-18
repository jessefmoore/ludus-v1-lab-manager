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

## Architecture

```
┌─────────────────────────────┐
│  React UI (Stitch design)   │
│  Instructor dashboard       │
└──────────────┬──────────────┘
               │ REST / JSON
               ▼
┌─────────────────────────────┐
│  FastAPI backend            │
│  - sessions / students      │
│  - ludus wrapper            │
│  - invites                  │
└──────┬──────────────┬───────┘
       │              │
       ▼              ▼
  [SQLite]       [Ludus API]
                 (one or more Ludus servers)
```

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic, httpx
- **Frontend:** React + TypeScript + Tailwind (Stitch-designed)
- **DB:** SQLite (MVP), Postgres (v2+)
- **Auth:** Single instructor account, JWT in httpOnly cookie
- **Deployment:** Docker Compose

## Project structure

```
insec-platform/
├── backend/
│   ├── app/
│   │   ├── api/                    # FastAPI route handlers
│   │   │   ├── auth.py             #   login / logout / me
│   │   │   ├── events.py           #   audit log
│   │   │   ├── invite.py           #   public invite + config download
│   │   │   ├── labs.py             #   lab templates CRUD + cover images
│   │   │   ├── ludus.py            #   Ludus range/snapshot/template proxy
│   │   │   ├── ludus_ansible.py    #   Ludus Ansible role management
│   │   │   ├── ludus_groups.py     #   Ludus group management
│   │   │   ├── ludus_testing.py    #   Ludus testing mode control
│   │   │   ├── sessions.py         #   training sessions CRUD + provision
│   │   │   ├── settings.py         #   platform settings + Ludus servers
│   │   │   └── students.py         #   student CRUD + CSV import + reset
│   │   ├── core/                   # App configuration and dependencies
│   │   │   ├── config.py           #   pydantic-settings (env vars)
│   │   │   ├── db.py               #   SQLAlchemy engine + session factory
│   │   │   ├── deps.py             #   FastAPI dependency injection
│   │   │   ├── limiter.py          #   rate limiting (slowapi)
│   │   │   └── security.py         #   JWT + password hashing
│   │   ├── middleware/             # CSRF protection, request logging
│   │   ├── models/                 # SQLAlchemy ORM models
│   │   │   ├── event.py            #   audit events
│   │   │   ├── lab_template.py     #   lab templates (range-config YAML)
│   │   │   ├── session.py          #   training sessions
│   │   │   ├── student.py          #   students + invite tokens
│   │   │   └── user.py             #   instructor account
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   ├── services/              # Business logic (no FastAPI imports)
│   │   │   ├── bootstrap.py        #   admin account seeding on startup
│   │   │   ├── invite.py           #   invite token + WireGuard config
│   │   │   ├── labs.py             #   lab template CRUD + cover images
│   │   │   ├── ludus.py            #   LudusClient — single Ludus integration point
│   │   │   ├── provision.py        #   bulk provisioning orchestrator
│   │   │   ├── sessions.py         #   session lifecycle
│   │   │   └── students.py         #   student management + CSV import
│   │   └── main.py                 # FastAPI app factory + startup
│   ├── alembic/                    # DB migrations
│   │   └── versions/
│   ├── tests/                      # pytest test suite
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/                    # API client + TypeScript types
│   │   ├── components/             # Reusable UI components
│   │   │   ├── AppLayout.tsx       #   sidebar + main content layout
│   │   │   ├── Button.tsx          #   button variants
│   │   │   ├── Card.tsx            #   card container
│   │   │   ├── CommandPalette.tsx   #   Cmd+K search palette
│   │   │   ├── DataTable.tsx       #   sortable data table
│   │   │   ├── Modal.tsx           #   dialog overlay
│   │   │   ├── RangeStatePill.tsx  #   Ludus range state indicator
│   │   │   ├── SessionTimeline.tsx #   session event timeline
│   │   │   ├── Sidebar.tsx         #   navigation sidebar
│   │   │   ├── StatusPill.tsx      #   student/session status badge
│   │   │   ├── Tabs.tsx            #   tab navigation
│   │   │   └── Toast.tsx           #   notification toasts
│   │   ├── contexts/               # React context (auth)
│   │   └── pages/                  # Page-level components
│   │       ├── Dashboard.tsx       #   overview + stats
│   │       ├── LabTemplates.tsx    #   lab template management
│   │       ├── Login.tsx           #   auth screen
│   │       ├── LudusManagement.tsx #   Ludus server admin
│   │       ├── SessionDetail.tsx   #   session + student management
│   │       └── Settings.tsx        #   platform settings
│   ├── Dockerfile
│   └── vite.config.ts
├── docs/                           # Architecture, roadmap, design system
├── data/                           # Runtime data (gitignored)
│   ├── configs/                    #   WireGuard .conf files
│   └── uploads/                    #   lab cover images
├── docker-compose.yml
├── Caddyfile                       # Reverse proxy config
├── .env.example
└── .github/workflows/              # CI (backend + frontend)
```

## Quick start

```bash
cp .env.example .env
# edit .env with your Ludus API key and admin password
docker compose up -d
```

## License

Private — all rights reserved (for now).
