"""Service layer for lab template persistence.

Pure DB logic; no FastAPI imports. Router layer is responsible for
translating ``ValueError`` into HTTP 422 and for access control.
"""

import logging

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.models.event import Event
from app.models.lab_template import LabTemplate
from app.models.session import Session as SessionModel
from app.models.session import SessionStatus
from app.schemas.lab import LabTemplateCreate, LabTemplateUpdate

logger = logging.getLogger(__name__)


class LabNotFound(Exception):  # noqa: N818 — spec-mandated name
    """Raised when a lab template id does not exist."""


class LabDeleteConflict(Exception):  # noqa: N818 — spec-mandated name
    """Raised when deleting a lab that has active (non-ended, non-draft) sessions."""


# Truncation limit for YAML parse-error detail strings surfaced to callers.
# Keeps 422 responses short when pyyaml emits multi-line diagnostics.
_YAML_ERROR_SNIPPET_MAX = 240


def list_labs(db: DBSession) -> list[LabTemplate]:
    """Return every lab template, oldest first (stable id order)."""
    stmt = select(LabTemplate).order_by(LabTemplate.id)
    return list(db.execute(stmt).scalars().all())


def get_lab(db: DBSession, lab_id: int) -> LabTemplate | None:
    """Return one lab template by id, or ``None`` if it doesn't exist."""
    return db.get(LabTemplate, lab_id)


def create_lab(db: DBSession, payload: LabTemplateCreate) -> LabTemplate:
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
            f"range_config_yaml must parse to a YAML mapping (dict), got {type(parsed).__name__}"
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


def update_lab(db: DBSession, lab_id: int, payload: LabTemplateUpdate) -> LabTemplate:
    """Apply a partial update to an existing lab template.

    YAML validation is the same as ``create_lab``: ``yaml.safe_load`` must
    succeed and produce a ``dict``.

    Raises:
        LabNotFound: if ``lab_id`` does not exist.
        ValueError: if ``range_config_yaml`` is invalid YAML or not a mapping.
    """
    lab = db.get(LabTemplate, lab_id)
    if lab is None:
        raise LabNotFound(f"Lab template {lab_id} not found")

    updates = payload.model_dump(exclude_unset=True)

    if "range_config_yaml" in updates:
        raw_yaml = updates["range_config_yaml"]
        try:
            parsed = yaml.safe_load(raw_yaml)
        except yaml.YAMLError as exc:
            snippet = str(exc)
            if len(snippet) > _YAML_ERROR_SNIPPET_MAX:
                snippet = snippet[:_YAML_ERROR_SNIPPET_MAX] + "..."
            raise ValueError(f"range_config_yaml is not valid YAML: {snippet}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                "range_config_yaml must parse to a YAML mapping (dict), "
                f"got {type(parsed).__name__}"
            )

    for key, value in updates.items():
        setattr(lab, key, value)

    event = Event(
        session_id=None,
        student_id=None,
        action="lab_template.updated",
        details_json={"lab_template_id": lab_id, "changed_fields": list(updates.keys())},
    )
    db.add(event)

    db.commit()
    db.refresh(lab)
    logger.info("lab_template.updated id=%s fields=%s", lab_id, list(updates.keys()))
    return lab


def delete_lab(db: DBSession, lab_id: int) -> None:
    """Delete a lab template if no active sessions reference it.

    Raises:
        LabNotFound: if ``lab_id`` does not exist.
        LabDeleteConflict: if any session with this template has a status
            other than ``draft`` or ``ended``.
    """
    lab = db.get(LabTemplate, lab_id)
    if lab is None:
        raise LabNotFound(f"Lab template {lab_id} not found")

    blocking = (
        db.execute(
            select(SessionModel).where(
                SessionModel.lab_template_id == lab_id,
                SessionModel.status.notin_([SessionStatus.ended, SessionStatus.draft]),
            )
        )
        .scalars()
        .first()
    )
    if blocking is not None:
        raise LabDeleteConflict(
            f"Cannot delete lab template {lab_id}: session {blocking.id} "
            f"is in status '{blocking.status}'"
        )

    event = Event(
        session_id=None,
        student_id=None,
        action="lab_template.deleted",
        details_json={"lab_template_id": lab_id, "name": lab.name},
    )
    db.add(event)

    db.delete(lab)
    db.commit()
    logger.info("lab_template.deleted id=%s name=%s", lab_id, lab.name)


__all__ = [
    "LabDeleteConflict",
    "LabNotFound",
    "create_lab",
    "delete_lab",
    "get_lab",
    "list_labs",
    "update_lab",
]
