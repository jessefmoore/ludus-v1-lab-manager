# Architecture

## Data model

```sql
users (
  id, email, password_hash, role, created_at
)

lab_templates (
  id, name, description,
  range_config_yaml,
  default_mode,            -- 'shared' | 'dedicated'
  ludus_server,
  entry_point_vm,          -- shown to student in invite page
  created_at
)

sessions (
  id, name, start_date, end_date,
  lab_template_id,
  mode,                    -- 'shared' | 'dedicated'
  shared_range_id,         -- if mode='shared'
  status,                  -- 'draft'|'provisioning'|'active'|'ended'
  created_at
)

students (
  id, session_id,
  full_name, email,
  ludus_userid,
  range_id,                -- if mode='dedicated'
  wg_config_path,
  invite_token,
  invite_redeemed_at,
  status,                  -- 'pending'|'ready'|'error'
  created_at
)

events (
  id, session_id, student_id,
  action, details_json,
  created_at
)
```

## Ludus client wrapper

`backend/app/services/ludus.py` is the single integration point with Ludus.
Every Ludus interaction goes through this class so we can:
- Swap CLI for HTTP API later
- Add retries/timeouts consistently
- Mock it in tests

```python
class LudusClient:
    def __init__(self, url: str, api_key: str, verify_tls: bool = False): ...

    def user_add(self, userid: str, name: str, email: str) -> dict: ...
    def user_rm(self, userid: str) -> None: ...
    def range_assign(self, userid: str, range_id: str) -> None: ...
    def user_wireguard(self, userid: str) -> str: ...  # returns .conf contents
    def snapshot_revert(self, userid: str, name: str) -> None: ...
    def range_deploy(self, userid: str, config_yaml: str) -> None: ...
    def range_list(self) -> list[dict]: ...
```

## Provisioning flow

```
POST /api/sessions/{id}/provision
    │
    ▼
for student in session.students:
    1. ludus.user_add(userid, name, email='<userid>@ctf.local')
    2. if mode == 'shared':
         ludus.range_assign(userid, session.shared_range_id)
       else:
         ludus.range_deploy(userid, lab_template.range_config_yaml)
    3. config = ludus.user_wireguard(userid)
    4. write config to data/configs/<session_id>/<userid>.conf
    5. student.invite_token = random_hex(16)
    6. student.status = 'ready'
    7. log event
```

MVP runs this synchronously in the request handler.
v2 will move to a background worker.

## Invite flow (public, no auth)

```
GET /invite/{token}
    ↓
Lookup student by invite_token
    ↓
Render HTML page:
  - Student name
  - Lab info (from template: entry_point_vm, description)
  - Download button → GET /invite/{token}/config
  - Expires info

GET /invite/{token}/config
    ↓
Serve file with Content-Disposition: attachment; filename=<userid>.conf
Mark student.invite_redeemed_at = now()
Log event
```

## Security considerations

- **Invite tokens:** cryptographically random, single-use optional, TTL enforced
- **WG configs on disk:** mode 0600, stored outside web root, served only via token
- **Ludus API key:** in `.env`, never logged, never exposed to frontend
- **CSRF:** platform uses JWT in httpOnly cookie + CSRF token for mutations
- **Rate limiting:** reset button per-student, provision per-session
- **Audit log:** all mutating actions recorded in `events` table
