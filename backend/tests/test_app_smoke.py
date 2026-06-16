"""End-to-end smoke test for the wired-up FastAPI application.

Exercises every Phase 1 endpoint against the *real* ``app.main.app`` via
``TestClient``, with only one surgical dependency override: ``get_ludus_client``
is replaced with a ``FakeLudus`` so we don't need a live Ludus server.

Env wiring is tricky because ``app.core.db`` builds its engine at module
import time from ``get_settings()``. This test uses a session-scoped
autouse fixture that sets every required env var *before* any ``app.*``
module is imported, then imports ``app.main`` lazily inside the test
itself. ``get_settings.cache_clear()`` is called too so the lru_cache
doesn't serve a stale Settings instance from a previous test run.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

_WG_TEMPLATE = "[Interface]\nPrivateKey = {userid}-priv\nAddress = 10.0.0.2/32\n"


class FakeLudus:
    """Minimal stand-in for ``LudusClient`` used by the smoke test."""

    def __init__(self) -> None:
        self.user_add_calls: list[dict[str, str]] = []
        self.range_assign_calls: list[dict[str, str]] = []
        self.range_deploy_calls: list[dict[str, str]] = []
        self.user_wireguard_calls: list[str] = []

    def user_add(self, userid: str, name: str, email: str) -> dict[str, Any]:
        self.user_add_calls.append({"userid": userid, "name": name, "email": email})
        return {"userID": userid, "name": name, "email": email}

    def range_list(self) -> list[dict]:
        return []

    def range_assign(self, userid: str, range_id: str) -> None:
        self.range_assign_calls.append({"userid": userid, "range_id": range_id})

    def range_deploy(self, userid: str, config_yaml: str) -> None:
        self.range_deploy_calls.append({"userid": userid, "config_yaml": config_yaml})

    def user_wireguard(self, userid: str) -> str:
        self.user_wireguard_calls.append(userid)
        return _WG_TEMPLATE.format(userid=userid)


@pytest.fixture(scope="module")
def _smoke_tmp_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Module-scoped temp dir used by the env-patching fixture below.

    Module-scoped so the ``autouse`` env fixture (also module-scoped) can
    depend on it without being reconstructed per test.
    """
    return tmp_path_factory.mktemp("smoke")


@pytest.fixture(scope="module", autouse=True)
def _smoke_env(_smoke_tmp_dir: Path) -> Iterator[dict[str, str]]:
    """Install env vars *before* any ``app.*`` import in this module.

    ``autouse=True`` at module scope guarantees pytest runs this before
    any test function body - and because we do NOT import ``app.main``
    at module top-level, the first import happens inside the test, AFTER
    this fixture has run. That keeps the engine in ``app.core.db``
    bound to our tmp sqlite file.
    """
    db_path = _smoke_tmp_dir / "test.db"
    configs_dir = _smoke_tmp_dir / "configs"

    configs_dir.mkdir(parents=True, exist_ok=True)

    patched: dict[str, str] = {
        "DATABASE_URL": f"sqlite:///{db_path}",
        "APP_ENV": "development",
        "APP_SECRET_KEY": "smoke-test-secret",
        "ADMIN_EMAIL": "admin@example.com",
        "ADMIN_PASSWORD": "test-pass-123",
        "LUDUS_DEFAULT_URL": "https://ludus.test",
        "LUDUS_DEFAULT_API_KEY": "test-key",
        "CONFIG_STORAGE_DIR": str(configs_dir),
        "PUBLIC_BASE_URL": "http://testapp.local",
    }
    previous: dict[str, str | None] = {k: os.environ.get(k) for k in patched}
    os.environ.update(patched)
    try:
        yield patched
    finally:
        for key, prior in previous.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


def test_app_smoke_exercises_every_phase1_endpoint(_smoke_env: dict[str, str]) -> None:
    """One big happy-path walk through the whole app.

    Health -> login -> lab -> session -> student -> provision -> invite page
    -> invite config download. Split into small assertion blocks so a
    failure pinpoints the broken step.
    """
    # Clear the settings cache so the env vars installed by the autouse
    # fixture actually take effect.
    from app.core.config import get_settings

    get_settings.cache_clear()

    # Import app LAZILY, after env vars are in place.
    from app.core.deps import get_ludus_client, get_ludus_client_registry
    from app.main import app

    fake_ludus = FakeLudus()

    class _FakeRegistry:
        def get(self, name: str = "default") -> FakeLudus:
            if name != "default":
                raise ValueError(f"Unknown Ludus server '{name}'")
            return fake_ludus

        @property
        def server_names(self) -> list[str]:
            return ["default"]

    app.dependency_overrides[get_ludus_client] = lambda: fake_ludus
    app.dependency_overrides[get_ludus_client_registry] = lambda: _FakeRegistry()

    try:
        with TestClient(app) as client:
            # 1. Liveness. DB + storage ok; Ludus unreachable in tests.
            r = client.get("/health")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"
            assert body["db"] is True
            assert body["storage"] is True

            # 2. Login with the admin creds the lifespan seeded.
            r = client.post(
                "/api/auth/login",
                json={
                    "email": _smoke_env["ADMIN_EMAIL"],
                    "password": _smoke_env["ADMIN_PASSWORD"],
                },
            )
            assert r.status_code == 200, r.text
            # The auth cookie is persisted on the TestClient so every
            # subsequent call is authenticated.
            assert any(c.name for c in client.cookies.jar if c.name), "expected a session cookie"

            # 3. /api/auth/me round-trips the cookie.
            r = client.get("/api/auth/me")
            assert r.status_code == 200
            assert r.json()["email"] == _smoke_env["ADMIN_EMAIL"]

            # 4. Create a lab template.
            r = client.post(
                "/api/labs",
                json={
                    "name": "Smoke Lab",
                    "description": "e2e smoke test lab",
                    "range_config_yaml": "ludus:\n  - vm_name: KALI\n",
                    "default_mode": "shared",
                    "ludus_server": "default",
                    "entry_point_vm": "KALI",
                },
            )
            assert r.status_code == 201, r.text
            lab_id = r.json()["id"]

            # 5. Create a shared session bound to range DEMO.
            r = client.post(
                "/api/sessions",
                json={
                    "name": "Smoke Cohort",
                    "lab_template_id": lab_id,
                    "mode": "shared",
                    "shared_range_id": "DEMO",
                },
            )
            assert r.status_code == 201, r.text
            session_body = r.json()
            session_id = session_body["id"]
            assert session_body["status"] == "draft"

            # 6. Enroll a student. The response carries the full invite URL,
            # so we can parse the token straight out of it.
            r = client.post(
                f"/api/sessions/{session_id}/students",
                json={"full_name": "Smoke Student", "email": "smoke@example.com"},
            )
            assert r.status_code == 201, r.text
            student_body = r.json()
            invite_url: str = student_body["invite_url"]
            assert invite_url.startswith(_smoke_env["PUBLIC_BASE_URL"])
            token = invite_url.rsplit("/invite/", 1)[-1]
            assert token, "failed to extract invite token from invite_url"

            # 7. Provision the session - talks to our FakeLudus + writes a
            # .conf file into CONFIG_STORAGE_DIR.
            r = client.post(f"/api/sessions/{session_id}/provision")
            assert r.status_code == 200, r.text
            prov_body = r.json()
            assert prov_body["provisioned"] == 1
            assert prov_body["failed"] == 0
            assert prov_body["skipped"] == 0

            # FakeLudus saw the shared-mode call pattern.
            assert len(fake_ludus.user_add_calls) == 1
            assert fake_ludus.range_assign_calls == [
                {"userid": fake_ludus.user_add_calls[0]["userid"], "range_id": "DEMO"}
            ]
            assert fake_ludus.range_deploy_calls == []
            assert fake_ludus.user_wireguard_calls == [fake_ludus.user_add_calls[0]["userid"]]

            # The provisioner wrote the config to disk at the documented
            # path layout.
            userid = fake_ludus.user_add_calls[0]["userid"]
            cfg_path = Path(_smoke_env["CONFIG_STORAGE_DIR"]) / str(session_id) / f"{userid}.conf"
            assert cfg_path.exists(), f"expected config at {cfg_path}"
            on_disk = cfg_path.read_bytes()
            assert on_disk.startswith(b"[Interface]")

            # 8. Public invite landing page (no auth). We drop the cookie
            # just to prove it's not required, then restore it.
            saved_cookies = dict(client.cookies)
            client.cookies.clear()
            r = client.get(f"/invite/{token}")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("text/html")
            assert "Smoke Student" in r.text

            # 9. Config download: served as an attachment, body equal to
            # what the provisioner wrote.
            r = client.get(f"/invite/{token}/config")
            assert r.status_code == 200, r.text
            disposition = r.headers.get("content-disposition", "")
            assert "attachment" in disposition
            assert f'filename="{userid}.conf"' in disposition
            assert r.content == on_disk

            # Restore instructor cookie for any future calls.
            for name, value in saved_cookies.items():
                client.cookies.set(name, value)
    finally:
        # Leave no dependency override behind for subsequent test modules
        # that might import ``app.main`` and share its module-level app.
        app.dependency_overrides.pop(get_ludus_client, None)
        app.dependency_overrides.pop(get_ludus_client_registry, None)
