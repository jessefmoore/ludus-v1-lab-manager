# ludus-v1-mgr

Training lab deployment management platform powered by [Ludus](https://ludus.cloud).

<img width="1343" height="752" alt="labmgr-v1" src="https://github.com/user-attachments/assets/ef91da24-0aa9-483e-a44e-3c7412bda76b" />


A self-hosted web platform that wraps [Ludus](https://ludus.cloud) to let instructors
provision, monitor, and tear down student lab environments in bulk for security
trainings and workshops.


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
- **Deployment:** Docker Compose (frontend nginx reverse proxy)


## Quick start

```bash
cp .env.example .env
# edit .env: set ADMIN_PASSWORD, APP_SECRET_KEY, LUDUS_DEFAULT_API_KEY
docker compose up -d
# UI at http://localhost (frontend nginx), API at http://localhost/api
```



### Credits
This was foked from https://github.com/whiteov3rflow/ludus-helm and modified to work with Ludus version 1

## License

[MIT](LICENSE)
