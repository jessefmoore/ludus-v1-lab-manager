# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**ludus-helm** is a self-hosted web platform that wraps [Ludus](https://ludus.cloud) to
let instructors bulk-provision student lab environments for security trainings (e.g.
[insec.ml](https://insec.ml) workshops). It replaces manual CLI workflows like creating
Ludus users, assigning ranges, and distributing WireGuard configs.

The repo is in **early MVP scaffolding stage** — most files described in
`docs/ARCHITECTURE.md` and `docs/ROADMAP.md` do not yet exist. When implementing, follow
the roadmap phases in order. Phase 1 is backend + Ludus wrapper; do not work on Phase 2
(frontend) until Phase 1's exit criteria (replacing the upstream `add_player.sh` via HTTP)
is met.

## Required reading before you edit anything

1. `docs/ARCHITECTURE.md` — data model, provisioning flow, Ludus wrapper contract
2. `docs/ROADMAP.md` — current phase and exit criteria
3. `docs/DESIGN_SYSTEM.md` — visual design tokens and component specs (frontend work)
4. `docs/AGENTS.md` — multi-agent role definitions and invocation templates
5. `docs/STITCH_PROMPTS.md` — archive of UI prompts (only needed if regenerating UI)

## Multi-agent workflow

This project uses a **five-role agent model** to keep concerns isolated and changes
reviewable. Do not attempt to do all roles at once — delegate via the Task tool using the
prompt templates in `docs/AGENTS.md`.

Roles:
- **Project Manager** — turns requests into specs + tasks (no code)
- **Backend Engineer** — owns `backend/` only
- **Frontend Engineer** — owns `frontend/` only
- **DevOps Engineer** — owns Dockerfiles, compose, CI, env
- **Supervisor** — read-only review, enforces architecture + DESIGN_SYSTEM.md compliance

Hard rules enforced by all roles and the Supervisor:
- **All Ludus interaction goes through `backend/app/services/ludus.py`.** No exceptions.
- **Backend never touches `frontend/` and vice versa.**
- **DevOps never modifies application code.**
- **PM and Supervisor never write code.**
- **Frontend must follow `docs/DESIGN_SYSTEM.md` exactly** — no ad-hoc colors/spacing.

## Architecture you must understand before editing

### The central abstraction: `LudusClient`

`backend/app/services/ludus.py` is the **single integration point with Ludus**. Every
Ludus interaction in the codebase must go through this class. Never call the `ludus` CLI
directly from other modules, never construct Ludus HTTP requests elsewhere. This is
non-negotiable because it lets us:
- Swap CLI for HTTP API without touching business logic
- Centralize retries/timeouts/error translation
- Mock Ludus in tests

The shape is defined in `docs/ARCHITECTURE.md` — methods like `user_add`, `range_assign`,
`user_wireguard`, `snapshot_revert`, `range_deploy`, `range_list`.

### The provisioning flow is the product

`POST /api/sessions/{id}/provision` is the core value of this platform. It orchestrates
per-student:
1. `ludus.user_add` → 2. `ludus.range_assign` (shared mode) OR `ludus.range_deploy`
   (dedicated mode) → 3. `ludus.user_wireguard` → 4. write `.conf` to disk →
5. generate invite token → 6. log event.

MVP runs this **synchronously** in the request handler. Do not introduce Celery/Redis
until Phase 4 — the roadmap is deliberate about keeping MVP blocking.

### Two deployment modes

Sessions have a `mode` field that changes provisioning semantics:
- `shared`: all students `range_assign`'d to a single pre-existing range (instructor
  deploys it manually first). Cheap on resources.
- `dedicated`: each student gets `range_deploy` of the template's YAML. Heavy on
  resources but isolated.

Any new feature must handle both modes. Don't assume dedicated by default.

### Invite flow is public and file-serving

`GET /invite/{token}` and `GET /invite/{token}/config` are the only unauthenticated
endpoints. The `.conf` file served here contains a WireGuard private key — treat these
paths with care: enforce token TTL, set file mode `0600` on disk, never log token values,
and serve with `Content-Disposition: attachment`.

### Sister project: grandline-lab

The Ludus range templates managed by this platform are produced by a separate repo at
`/home/rez/Research/HNx05/grandline-lab`. When debugging provisioning issues, the
underlying lab YAML and ansible roles live there — not here. This platform does not
re-implement lab logic; it only calls Ludus.

## Stack and conventions

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic 2, httpx, Alembic.
- **Frontend:** React + TypeScript + Vite + Tailwind. Initial page components are
  generated via Google Stitch (prompts archived in `docs/STITCH_PROMPTS.md`) and
  dropped into `frontend/src/pages/` as `Login.tsx`, `Dashboard.tsx`, `SessionDetail.tsx`,
  `Invite.tsx`. If Stitch output is unavailable or off-spec, `docs/DESIGN_SYSTEM.md`
  contains enough detail to hand-code the UI faithfully.
- **DB:** SQLite only for MVP (`DATABASE_URL=sqlite:///./data/insec.db`). Postgres is
  v2+. Migrations run via Alembic.
- **Auth:** Single instructor account bootstrapped from `ADMIN_EMAIL`/`ADMIN_PASSWORD`
  env vars. JWT lives in an httpOnly cookie. No OAuth, no RBAC in MVP.
- **Ruff config** in `backend/pyproject.toml` — line length 100, rule set includes
  `E, F, W, I, N, UP, B, A, C4, SIM, RUF`. Honor it.
- **Ludus server config:** discovered via env vars following the pattern
  `LUDUS_<NAME>_URL` / `LUDUS_<NAME>_API_KEY` / `LUDUS_<NAME>_VERIFY_TLS`. `DEFAULT` is
  bootstrapped; additional servers are v2.

## Commands

Most commands below assume the planned layout; they will fail until Phase 1 code lands.

### Local dev (backend)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload --port 8000
```

### Local dev (frontend)

```bash
cd frontend
npm install
npm run dev          # Vite dev server on :3000
```

### Docker Compose (all-in-one)

```bash
cp .env.example .env
# edit .env: ADMIN_PASSWORD, LUDUS_DEFAULT_API_KEY, APP_SECRET_KEY
docker compose up -d --build
docker compose logs -f backend
```

### Tests

```bash
cd backend
pytest                          # full suite
pytest tests/test_ludus.py      # one file
pytest -k "provision"           # pattern match
pytest -xvs tests/test_foo.py::test_bar   # single test, verbose, stop on first fail
```

### Lint / typecheck

```bash
cd backend
ruff check .
ruff format .
mypy app
```

### Database migrations

```bash
cd backend
alembic revision --autogenerate -m "add students table"
alembic upgrade head
alembic downgrade -1
```

## Current scaffold status

- `backend/app/main.py` currently exposes only `GET /health`. Auth, models, routers,
  and `services/ludus.py` are **not yet implemented**.
- `frontend/` has `package.json` + `Dockerfile` but no `src/`, no `vite.config.ts`, no
  Tailwind config. These must be added when the Stitch-generated components are
  integrated (or when hand-implementing against `docs/DESIGN_SYSTEM.md`).
- No Alembic setup yet — `alembic init alembic` must be run inside `backend/` before
  running migration commands.
- `data/configs/` is gitignored and contains WireGuard private keys at runtime — never
  commit, never log contents.

## Known Stitch quirks (frontend-relevant)

See `docs/STITCH_PROMPTS.md` § "Known Stitch quirks" for failure modes observed during
initial design generation. Most notably, Stitch consistently fails to render the sidebar
tagline with normal letter-spacing — fix this in the exported code, do not re-prompt.
