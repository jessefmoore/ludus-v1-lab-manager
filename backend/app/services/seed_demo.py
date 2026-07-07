"""Idempotent demo seed: lab templates from Ludus ranges + a sample session.

Run inside the backend container:

    python -m app.services.seed_demo
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.deps import _merge_servers
from app.models import LabTemplate, Session as SessionRow
from app.models.lab_template import LabTemplateMode
from app.models.session import SessionMode, SessionStatus
from app.schemas.lab import LabTemplateCreate
from app.schemas.session import SessionCreate
from app.schemas.student import StudentCreate
from app.services import labs as labs_service
from app.services import sessions as sessions_service
from app.services import students as students_service
from app.services.exceptions import LudusError
from app.services.ludus import LudusClient

logger = logging.getLogger(__name__)

DEMO_SESSION_NAME = "LeHack 2026 Demo"

LAB_TARGETS: list[dict[str, str]] = [
    {
        "name": "Grand Line CTF 2",
        "description": "CTF range on the research Ludus server.",
        "ludus_server": "research",
        "range_id": "RZ2",
        "default_mode": "shared",
        "entry_point_vm": "RZ2-MARINEFORD",
    },
    {
        "name": "GOAD Light",
        "description": "Active Directory attack lab on the default Ludus server.",
        "ludus_server": "default",
        "range_id": "GOADLight3c1abb",
        "default_mode": "dedicated",
        "entry_point_vm": "GOAD-DC01",
    },
]

DEMO_STUDENTS: list[tuple[str, str]] = [
    ("Alice Demo", "alice.demo@example.com"),
    ("Bob Demo", "bob.demo@example.com"),
    ("Charlie Demo", "charlie.demo@example.com"),
]


def _find_range(client: LudusClient, range_id: str) -> dict | None:
    # Ludus v1 keys ranges by the owning user's ID (there is no rangeID
    # string); ``range_id`` here is treated as that owner userID.
    for row in client.range_list():
        if row.get("userID") == range_id:
            return row
    return None


def _fetch_range_yaml(client: LudusClient, *, range_id: str, range_number: int | None) -> str:
    # On Ludus v1, a range's config is fetched by the owning user's ID.
    # ``range_id`` is the owner userID; ``range_number`` (if any) is only
    # used to locate that owner in the user/range list.
    candidate_user_ids: list[str] = [range_id]

    if range_number is not None:
        for row in client.range_list():
            if row.get("rangeNumber") == range_number:
                owner = row.get("userID")
                if owner and owner not in candidate_user_ids:
                    candidate_user_ids.append(owner)

    for user_id in candidate_user_ids:
        try:
            return client.range_get_config(user_id=user_id)
        except LudusError:
            continue

    try:
        return client.range_config_example()
    except LudusError as exc:
        raise RuntimeError(f"Could not fetch range config for {range_id}") from exc


def _get_or_create_lab(
    db,
    settings: Settings,
    *,
    target: dict[str, str],
    config_yaml: str,
) -> LabTemplate:
    existing = db.execute(
        select(LabTemplate).where(LabTemplate.name == target["name"])
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    mode = LabTemplateMode.shared if target["default_mode"] == "shared" else LabTemplateMode.dedicated
    payload = LabTemplateCreate(
        name=target["name"],
        description=target["description"],
        range_config_yaml=config_yaml,
        default_mode=mode,
        ludus_server=target["ludus_server"],
        entry_point_vm=target.get("entry_point_vm"),
    )
    return labs_service.create_lab(db, payload)


def seed_demo_data(settings: Settings | None = None) -> dict[str, object]:
    """Seed demo labs and a draft session. Safe to run multiple times."""
    settings = settings or get_settings()
    db = SessionLocal()
    created: dict[str, object] = {"labs": [], "session_id": None, "students_added": 0}

    try:
        servers = _merge_servers(db, settings)
        lab_by_name: dict[str, LabTemplate] = {}

        for target in LAB_TARGETS:
            server_name = target["ludus_server"]
            if server_name not in servers:
                logger.warning("Skipping lab %s: server %s not configured", target["name"], server_name)
                continue

            cfg = servers[server_name]
            client = LudusClient(cfg.url, cfg.api_key, cfg.verify_tls)
            try:
                match = _find_range(client, target["range_id"])
                if match is None:
                    logger.warning("Range %s not found on %s", target["range_id"], server_name)
                    continue
                range_number = match.get("rangeNumber")
                yaml_text = _fetch_range_yaml(
                    client,
                    range_id=target["range_id"],
                    range_number=range_number if isinstance(range_number, int) else None,
                )
                lab = _get_or_create_lab(db, settings, target=target, config_yaml=yaml_text)
                lab_by_name[lab.name] = lab
                created["labs"].append(lab.name)
            finally:
                client.close()

        demo_lab = lab_by_name.get("Grand Line CTF 2") or next(iter(lab_by_name.values()), None)
        if demo_lab is None:
            raise RuntimeError("No lab templates were seeded; check Ludus connectivity")

        session = db.execute(
            select(SessionRow)
            .options(joinedload(SessionRow.students))
            .where(SessionRow.name == DEMO_SESSION_NAME)
        ).unique().scalar_one_or_none()

        if session is None:
            session = sessions_service.create_session(
                db,
                SessionCreate(
                    name=DEMO_SESSION_NAME,
                    lab_template_id=demo_lab.id,
                    mode=SessionMode.shared if demo_lab.default_mode == LabTemplateMode.shared else SessionMode.dedicated,
                    shared_range_id="RZ2" if demo_lab.name == "Grand Line CTF 2" else None,
                ),
            )
            created["session_created"] = True
        else:
            created["session_created"] = False

        created["session_id"] = session.id

        existing_emails = {
            s.email.lower()
            for s in session.students
        }
        for full_name, email in DEMO_STUDENTS:
            if email.lower() in existing_emails:
                continue
            students_service.create_student(
                db,
                session.id,
                StudentCreate(full_name=full_name, email=email),
            )
            created["students_added"] = int(created["students_added"]) + 1

        db.commit()
        return created
    finally:
        db.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        result = seed_demo_data()
    except Exception:
        logger.exception("Demo seed failed")
        return 1

    labs = result.get("labs", [])
    print(f"Labs ready: {', '.join(labs) if labs else 'none'}")
    print(f"Session: {DEMO_SESSION_NAME} (id={result.get('session_id')})")
    print(f"New students added: {result.get('students_added', 0)}")
    print(f"Session newly created: {result.get('session_created', False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
