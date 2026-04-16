"""Service layer for lab template persistence.

Pure DB logic; no FastAPI imports. Router layer is responsible for
translating ``ValueError`` into HTTP 422 and for access control.
"""

import logging

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.lab_template import LabTemplate
from app.schemas.lab import LabTemplateCreate

logger = logging.getLogger(__name__)

# Truncation limit for YAML parse-error detail strings surfaced to callers.
# Keeps 422 responses short when pyyaml emits multi-line diagnostics.
_YAML_ERROR_SNIPPET_MAX = 240


def list_labs(db: Session) -> list[LabTemplate]:
    """Return every lab template, oldest first (stable id order)."""
    stmt = select(LabTemplate).order_by(LabTemplate.id)
    return list(db.execute(stmt).scalars().all())


def get_lab(db: Session, lab_id: int) -> LabTemplate | None:
    """Return one lab template by id, or ``None`` if it doesn't exist."""
    return db.get(LabTemplate, lab_id)


def create_lab(db: Session, payload: LabTemplateCreate) -> LabTemplate:
    """Validate YAML, persist a new LabTemplate, log an audit event.

    YAML validation rules:
    * ``yaml.safe_load`` must succeed.
    * The parsed document must be a ``dict`` (Ludus range-config shape).

    Raises ``ValueError`` on invalid YAML; the router converts it to
    HTTP 422. ``ValueError.args[0]`` carries a short, caller-safe message.
    """
    try:
        parsed = yaml.safe_load(payload.range_config_yaml)
    except yaml.YAMLError as exc:
        snippet = str(exc)
        if len(snippet) > _YAML_ERROR_SNIPPET_MAX:
            snippet = snippet[:_YAML_ERROR_SNIPPET_MAX] + "..."
        logger.info("lab_template.create rejected: invalid YAML")
        raise ValueError(f"range_config_yaml is not valid YAML: {snippet}") from exc

    if not isinstance(parsed, dict):
        logger.info(
            "lab_template.create rejected: YAML parsed to %s, expected mapping",
            type(parsed).__name__,
        )
        raise ValueError(
            "range_config_yaml must parse to a YAML mapping (dict), "
            f"got {type(parsed).__name__}"
        )

    lab = LabTemplate(
        name=payload.name,
        description=payload.description,
        range_config_yaml=payload.range_config_yaml,
        default_mode=payload.default_mode,
        ludus_server=payload.ludus_server,
        entry_point_vm=payload.entry_point_vm,
    )
    db.add(lab)
    db.flush()  # assign lab.id before we reference it in the event payload

    event = Event(
        session_id=None,
        student_id=None,
        action="lab_template.created",
        details_json={"lab_template_id": lab.id, "name": lab.name},
    )
    db.add(event)

    db.commit()
    db.refresh(lab)
    logger.info("lab_template.created id=%s name=%s", lab.id, lab.name)
    return lab


__all__ = ["create_lab", "get_lab", "list_labs"]
