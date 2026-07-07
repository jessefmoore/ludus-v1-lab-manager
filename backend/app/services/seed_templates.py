"""Seed the ``lab_templates`` table with a starter pack of Ludus v1 range configs.

The YAML files in ``app/seed_templates/`` are curated, deployable Ludus v1
range configs (from github.com/jessefmoore/Ludus-Ranges, with GOAD/``goad.sh``
configs excluded). On first startup — tracked per ``SEED_VERSION`` via an
``Event`` sentinel — they are imported as ``LabTemplate`` rows so instructors
have ready-to-deploy templates in the UI.

Idempotent and delete-respecting: once a version has been seeded, it is not
re-seeded, so removing a seeded template in the UI sticks across restarts. Bump
``SEED_VERSION`` to ship a new/updated pack.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.config import Settings
from app.models.event import Event
from app.models.lab_template import LabTemplate, LabTemplateMode

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parent.parent / "seed_templates"
SEED_VERSION = "1"
_SENTINEL_ACTION = "lab_templates.seeded"


def _summarize(config: dict) -> tuple[str, str | None]:
    """Return a short human description and a best-guess entry-point VM name."""
    vms = config.get("ludus")
    if not isinstance(vms, list) or not vms:
        return ("Ludus range config", None)

    windows = sum(1 for v in vms if isinstance(v, dict) and "windows" in v)
    linux = sum(1 for v in vms if isinstance(v, dict) and v.get("linux"))
    has_domain = any(isinstance(v, dict) and "domain" in v for v in vms)

    parts = [f"{len(vms)} VM" + ("s" if len(vms) != 1 else "")]
    if windows:
        parts.append(f"{windows} Windows")
    if linux:
        parts.append(f"{linux} Linux")
    if has_domain:
        parts.append("AD domain")

    entry: str | None = None
    for v in vms:
        if isinstance(v, dict) and "kali" in str(v.get("vm_name", "")).lower():
            entry = v.get("vm_name")
            break

    return (", ".join(parts), entry)


def _already_seeded(db: DBSession, version: str) -> bool:
    rows = db.execute(select(Event).where(Event.action == _SENTINEL_ACTION)).scalars().all()
    return any((e.details_json or {}).get("version") == version for e in rows)


def seed_lab_templates(db: DBSession, settings: Settings) -> int:
    """Import the bundled starter range configs as lab templates (once per version).

    Returns the number of templates created. No-op when disabled via
    ``SEED_LAB_TEMPLATES=false`` or when this ``SEED_VERSION`` was already seeded.
    """
    if not getattr(settings, "seed_lab_templates", True):
        return 0
    if _already_seeded(db, SEED_VERSION):
        return 0
    if not SEED_DIR.is_dir():
        logger.warning("seed_lab_templates: directory not found: %s", SEED_DIR)
        return 0

    created = 0
    for path in sorted(SEED_DIR.glob("*.yml")):
        name = path.stem
        existing = db.execute(
            select(LabTemplate).where(LabTemplate.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            continue

        raw = path.read_text(encoding="utf-8")
        try:
            parsed = yaml.safe_load(raw)
        except yaml.YAMLError:
            logger.warning("seed_lab_templates: skipping invalid YAML %s", path.name)
            continue
        if not isinstance(parsed, dict) or not isinstance(parsed.get("ludus"), list):
            logger.warning("seed_lab_templates: skipping non-range config %s", path.name)
            continue

        description, entry_point = _summarize(parsed)
        db.add(
            LabTemplate(
                name=name,
                description=description,
                range_config_yaml=raw,
                default_mode=LabTemplateMode.dedicated,
                ludus_server="default",
                entry_point_vm=entry_point,
            )
        )
        created += 1

    db.add(
        Event(
            session_id=None,
            student_id=None,
            action=_SENTINEL_ACTION,
            details_json={"version": SEED_VERSION, "count": created},
        )
    )
    db.commit()
    logger.info(
        "seed_lab_templates: created %d starter templates (version %s)",
        created,
        SEED_VERSION,
    )
    return created


__all__ = ["seed_lab_templates", "SEED_VERSION"]
