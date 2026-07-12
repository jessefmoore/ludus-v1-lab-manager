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

## Connecting to Ludus

Ludus v1 exposes **two** API ports, and this platform needs both:

- **`:8080`** — user API (all interfaces). Ranges, snapshots, WireGuard configs, testing.
- **`:8081`** — admin API (**`127.0.0.1` only**). Creating and deleting Ludus users. Bulk
  provision and teardown fail without it.

Because the admin API is bound to localhost on the Ludus host, expose it to this platform
with a **source-restricted socat proxy** running on the Ludus host as a systemd service. It
forwards a non-loopback port back to `127.0.0.1:8081`, restricted to the manager's IP:

```ini
# /etc/systemd/system/ludus-admin-proxy.service  (on the Ludus host)
[Unit]
Description=Ludus admin API proxy (source-restricted)
After=network-online.target
Wants=network-online.target

[Service]
# range= locks the source to the manager box only; still API-key protected behind it.
# Raw TCP passthrough: TLS stays end-to-end between the manager and :8081.
ExecStart=/usr/bin/socat \
  TCP-LISTEN:18081,bind=<ludus-host-ip>,reuseaddr,fork,range=<manager-ip>/32 \
  TCP:127.0.0.1:8081
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now ludus-admin-proxy.service
```

Then point `.env` at the two endpoints (use an **admin** Ludus user's API key):

```bash
LUDUS_DEFAULT_URL=https://<ludus-host-ip>:8080        # user API
LUDUS_DEFAULT_ADMIN_URL=https://<ludus-host-ip>:18081 # admin API via the proxy above
LUDUS_DEFAULT_API_KEY=<admin-ludus-user-api-key>
LUDUS_DEFAULT_VERIFY_TLS=false                        # Ludus uses a self-signed cert
```

See `.env.example` for the full list of Ludus variables.

### Credits
This was foked from https://github.com/whiteov3rflow/ludus-helm and modified to work with Ludus version 1

## License

[MIT](LICENSE)
