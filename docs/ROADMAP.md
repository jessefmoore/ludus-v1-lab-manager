# Roadmap

## Phase 1 — Core backend + Ludus wrapper (MVP) :white_check_mark:

- [x] FastAPI project scaffold (`pyproject.toml`, `main.py`, settings)
- [x] SQLite + SQLAlchemy models (users, lab_templates, sessions, students, events)
- [x] Auth (single instructor)
- [x] `services/ludus.py` — HTTP client wrapping Ludus API
  - [x] `user_add(userid, name, email, password) -> User`
  - [x] `user_rm(userid) -> None`
  - [x] `range_assign(userid, range_id) -> None`
  - [x] `user_wireguard(userid) -> str`  (returns .conf text)
  - [x] `snapshot_revert(userid, name) -> None`
  - [x] `range_deploy(userid, config_yaml) -> None`  (for dedicated mode)
- [x] Endpoints:
  - [x] `POST /api/auth/login`
  - [x] `GET/POST /api/labs`
  - [x] `GET/POST /api/sessions`
  - [x] `POST /api/sessions/{id}/provision`
  - [x] `POST /api/sessions/{id}/students`
  - [x] `POST /api/students/{id}/reset`
  - [x] `DELETE /api/students/{id}`
  - [x] `GET /invite/{token}` (public, HTML)
  - [x] `GET /invite/{token}/config` (public, .conf download)

**Exit criteria:** Replace `add_player.sh` end-to-end via curl/HTTP. **MET**

## Phase 2 — Frontend :white_check_mark:

- [x] Design for 4 screens (Login, Dashboard, Session Detail, LabTemplates)
  - _Hand-coded from DESIGN_SYSTEM.md. Invite page is server-rendered HTML by the backend, correctly excluded from frontend routes._
- [x] React + Tailwind in `frontend/` (27 source files)
- [x] Wire pages to backend API (typed API client with all endpoints)
- [x] Auth flow (login -> dashboard -> logout) via AuthContext + ProtectedRoute + Sidebar logout
- [x] Create session -> add students -> provision flow (Dashboard create modal -> SessionDetail add student modal -> Provision All)
- [x] Live student table with status polling

**Exit criteria:** Click-through from login to inviting a student in the browser. **MET**

## Phase 3 — Polish :white_check_mark:

- [x] CSV bulk import for students
- [x] Provisioning progress indicator (polling-based progress bar)
- [x] Rate-limited reset button (2-min cooldown, HTTP 429)
- [x] Session teardown confirmation modal
- [x] Audit log view (`GET /api/events` + collapsible Activity Log panel)
- [x] Basic error handling + toast notifications
- [x] Ludus management page (8 tabs: ranges, snapshots, templates, users, groups, ansible, testing, logs)
- [x] Ludus user management (create/delete users, WireGuard config download, API key display)
- [x] Full Ludus API wrapper (40+ endpoints: power, snapshots, templates, groups, ansible, testing, logs, range detail)
- [x] Multi-Ludus-server support (`LudusClientRegistry`, server selector UI, `?server=` query param)
- [x] Command palette (`Ctrl+K` quick-navigate)
- [x] Settings page (platform config, password change, Ludus connection test)
- [x] Reusable UI components (DataTable, Tabs, Skeleton, PageTransition)

**Exit criteria:** Run first real training on the platform.

## Phase 4 — v2 (post-MVP)

- [ ] SMTP email delivery of invites
- [ ] Multi-instructor / RBAC
- [ ] Postgres migration
- [ ] Background job queue (Celery + Redis)
- [ ] Public signup / landing page
