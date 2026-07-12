# Session resource management: quotas, capacity, lifecycle, user IDs & shared ranges

Builds a full resource-management and lifecycle layer on top of the Ludus
session workflow. Five self-contained, per-feature commits.

## What's included

### 1. CPU/RAM resource quotas (`a4e97be`)
- Per-session budget (`cpu_quota` / `ram_quota_gb`, migration `0004`) enforced as a
  **hard block at provision time (409)** before any Ludus call.
- Global per-range cap (`MAX_RANGE_CPUS` / `MAX_RANGE_RAM_GB`) validated when a lab
  template is saved (422).
- `GET /api/sessions/{id}/quota` preflight; Resource Budget card in the UI.
- Budget computed from each range config's `cpus`/`ram_gb` (`resources.py`).

### 2. Host CPU/RAM capacity dashboard (`8599251`)
- Shows how much CPU/RAM is still assignable on a host before creating a session.
- Capacity is configured manually (Ludus v1 has no host-resource endpoint): env
  `LUDUS_DEFAULT_CPU_CAPACITY` / `LUDUS_DEFAULT_RAM_CAPACITY_GB` for the default host,
  or `cpu_capacity`/`ram_capacity_gb` columns on `ludus_servers` (migration `0005`).
- Allocation = CPU/RAM committed by the app's live sessions' **deployed** ranges.
- `GET /api/ludus/capacity`; Dashboard card with overcommit warning.

### 3. Session lifecycle & resource management (`e6d438c`)
- **Tear Down / Rebuild** replace the no-op "End Session": rebuild destroys VMs but
  keeps users (re-provision for fresh VMs); teardown removes users + configs and
  marks the session ended.
- **Remove Range** per student (destroy VMs, keep the Ludus user) with a new
  **`Range-Removed`** status (migration `0006`).
- **Auto baseline snapshots**: once a range reaches `SUCCESS`, the session page
  snapshots it (disk-only, no RAM) so **Reset Environment** works; default snapshot
  renamed `ctf-initial` → `snapshot-1` and configurable at reset time.
- **Editable quota** (any time except when ended) and a Resource Budget card showing
  **allocated** (deployed ranges only — drops when a range is removed) vs quota; the
  over-budget gate still uses the full planned footprint.
- Endpoints: `POST /sessions/{id}/rebuild|teardown|baseline-snapshots`,
  `DELETE /students/{id}/range`.

### 4. Explicit & prefixed Ludus user IDs (`9b0a214`)
- Set a student's exact `ludus_userid` at enrollment (e.g. to reuse an existing empty
  range), validated against Ludus's `^[A-Za-z0-9]{1,20}$`.
- Auto-generated IDs can carry a prefix via `STUDENT_USERID_PREFIX` (sanitized to
  `[a-z0-9]`).

### 5. Shared-range owner enrollment & owner-aware actions (`43728ec`)
- Creating a **shared** session with a picked range auto-enrolls the range's owner as
  a student; provisioning treats them as the lead (owns the range — no redeploy/grant,
  just fetches their WireGuard config), while everyone added shares via cross-range
  access.
- Per-student action is owner-aware: **Remove Range** for the owner (and dedicated
  students), **Remove User** (revoke access) for non-owner sharers.

## Behavior notes for reviewers
- **Allocation vs demand:** "allocated" = deployed (`ready`) ranges; "demand"/gate =
  full planned footprint (all enrolled students). Dedicated scales per student; shared
  is one range regardless of headcount.
- Baseline snapshots are idempotent, patient (retry until `SUCCESS`), and disk-only to
  save space.
- Teardown/rebuild are best-effort per student; a failure marks that student `error`
  but never strands the batch.

## Migrations
`0004` (session quota) · `0005` (server capacity) · `0006` (`range_removed` enum) —
applied automatically on backend start in production.

## New config (env)
`MAX_RANGE_CPUS`, `MAX_RANGE_RAM_GB`, `LUDUS_DEFAULT_CPU_CAPACITY`,
`LUDUS_DEFAULT_RAM_CAPACITY_GB`, `STUDENT_USERID_PREFIX` — all optional.

## Testing
Full backend suite green (**477 passing**); new suites for resources, capacity,
teardown, snapshots, remove-range, and shared-range owner/lead behavior. Frontend
`tsc` + `vite build` clean.

## Deploy dependency (not in this repo)
Provisioning requires the manager to reach the Ludus **admin API** (`user_add`), which
is localhost-only on the Ludus host. This needs a source-restricted proxy on the host
(`ludus-admin-proxy`) and `LUDUS_DEFAULT_ADMIN_URL` pointed at it — see
`proxmoxtroubleshootgui.md` for the exact setup.
