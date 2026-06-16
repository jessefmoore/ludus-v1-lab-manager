# Production Deployment Checklist

## Secrets to rotate before first production deploy

- [ ] **`APP_SECRET_KEY`** - Generate a 64-char random hex:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
  Changing this invalidates all active sessions (instructors must re-login).

- [ ] **`ADMIN_PASSWORD`** - Set a strong password for the bootstrap admin account.
  Only takes effect on first startup (when no user with `ADMIN_EMAIL` exists).

- [ ] **`POSTGRES_PASSWORD`** - Set a unique database password.

- [ ] **`DOMAIN`** - Set to your real domain (e.g. `platform.insec.ml`).
  Caddy auto-provisions a Let's Encrypt certificate for this domain.
  Ensure ports 80 and 443 are open and the DNS A record points to your server.

- [ ] **`PUBLIC_BASE_URL`** - Set to `https://{DOMAIN}` (must match the Caddy domain).
  Used for invite links shared with students and CORS allow-list.

- [ ] **`LUDUS_DEFAULT_API_KEY`** - Set to the production Ludus admin API key.

## Deploy

```bash
docker compose up -d --build
```

Caddy serves HTTPS on 443, auto-redirects 80 to 443.
Backend and frontend are internal-only (no exposed ports).

## Verify

```bash
curl -s https://your-domain/health | jq .
# Should return: {"status": "ok", "db": true, "storage": true, "ludus": true}
```
