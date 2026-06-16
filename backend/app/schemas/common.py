"""Shared schema primitives.

Design note on enums: the ORM layer already defines ``LabTemplateMode``,
``SessionStatus`` and ``StudentStatus`` as ``enum.StrEnum`` values. Those
are directly Pydantic-compatible (Pydantic 2 accepts subclasses of
``str`` + ``enum.Enum``). We re-export them here under stable, schema-layer
names so that:

* Request/response shapes don't leak ORM-specific names.
* A future wire-format tweak (e.g. renaming a value) only touches this module.
* ``LabMode`` is a single type used by both ``LabTemplate`` and ``Session``
  because the two share the same "shared" / "dedicated" vocabulary.

The underlying identity is preserved (``LabMode is LabTemplateMode``), so
``model_validate`` on an ORM instance will accept the enum value without
conversion.
"""

from app.models import LabTemplateMode as LabMode
from app.models import SessionStatus, StudentStatus

__all__ = ["LabMode", "SessionStatus", "StudentStatus"]
