"""Tests for Pydantic schemas: validation + from-attributes round trips."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import (
    LabTemplate,
    LabTemplateMode,
    Session,
    SessionMode,
    Student,
)
from app.models import (
    SessionStatus as OrmSessionStatus,
)
from app.models import (
    StudentStatus as OrmStudentStatus,
)
from app.schemas import (
    InvitePageData,
    LabMode,
    LabTemplateCreate,
    LabTemplateRead,
    SessionCreate,
    SessionRead,
    SessionStatus,
    StudentCreate,
    StudentRead,
    StudentStatus,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orm_session() -> OrmSession:
    """A fresh in-memory sqlite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Re-export / public-surface smoke
# ---------------------------------------------------------------------------


def test_public_symbols_importable() -> None:
    """Every public schema symbol is re-exported from app.schemas."""
    from app import schemas

    for name in (
        "LabMode",
        "SessionStatus",
        "StudentStatus",
        "LabTemplateCreate",
        "LabTemplateRead",
        "SessionCreate",
        "SessionRead",
        "StudentCreate",
        "StudentRead",
        "InvitePageData",
    ):
        assert hasattr(schemas, name), f"missing re-export: {name}"


def test_lab_mode_is_stable_alias_of_orm_enum() -> None:
    """LabMode is the ORM's LabTemplateMode to keep wire + storage in sync."""
    assert LabMode is LabTemplateMode
    assert LabMode.shared.value == "shared"
    assert LabMode.dedicated.value == "dedicated"


# ---------------------------------------------------------------------------
# Create-schema validation
# ---------------------------------------------------------------------------


def test_lab_template_create_happy_path() -> None:
    """LabTemplateCreate accepts a minimal, valid payload."""
    payload = LabTemplateCreate(
        name="AD Basics",
        description="Intro AD lab",
        range_config_yaml="ludus: []\n",
        default_mode=LabMode.dedicated,
        entry_point_vm="KALI",
    )
    assert payload.name == "AD Basics"
    assert payload.default_mode == LabMode.dedicated
    assert payload.ludus_server == "default"  # default applied
    assert payload.entry_point_vm == "KALI"


def test_lab_template_create_accepts_string_mode() -> None:
    """StrEnum values coerce from their string representation."""
    payload = LabTemplateCreate(
        name="X",
        range_config_yaml="ludus: []\n",
        default_mode="shared",
    )
    assert payload.default_mode == LabMode.shared


def test_session_create_shared_without_range_id_is_valid() -> None:
    """mode=shared + shared_range_id=None is allowed (provisioner may fill it)."""
    payload = SessionCreate(
        name="Cohort A",
        lab_template_id=1,
        mode=LabMode.shared,
    )
    assert payload.mode == LabMode.shared
    assert payload.shared_range_id is None


def test_session_create_dedicated_with_range_id_is_allowed() -> None:
    """mode=dedicated + shared_range_id=<value> is not rejected (see docstring)."""
    payload = SessionCreate(
        name="Cohort B",
        lab_template_id=1,
        mode=LabMode.dedicated,
        shared_range_id="RZ42",
    )
    assert payload.mode == LabMode.dedicated
    assert payload.shared_range_id == "RZ42"


def test_student_create_happy_path() -> None:
    """StudentCreate accepts a valid email."""
    payload = StudentCreate(full_name="Alice Example", email="alice@example.com")
    assert payload.email == "alice@example.com"


def test_student_create_rejects_invalid_email() -> None:
    """StudentCreate raises ValidationError for an obviously malformed email."""
    with pytest.raises(ValidationError):
        StudentCreate(full_name="Alice", email="not-an-email")


def test_invite_page_data_happy_path() -> None:
    """InvitePageData validates a plausible render payload."""
    data = InvitePageData(
        student_name="Alice",
        lab_name="AD Basics",
        lab_description=None,
        entry_point_vm="KALI",
        expires_at=datetime(2026, 5, 1, tzinfo=UTC),
        download_url="http://localhost:8000/invite/tok/download",
    )
    assert data.lab_name == "AD Basics"
    assert data.expires_at.tzinfo is not None


# ---------------------------------------------------------------------------
# from_attributes round-trip against ORM instances
# ---------------------------------------------------------------------------


def test_round_trip_from_orm(orm_session: OrmSession) -> None:
    """Read schemas validate straight from the ORM objects."""
    template = LabTemplate(
        name="AD Basics",
        description="Intro AD lab",
        range_config_yaml="ludus: []\n",
        default_mode=LabTemplateMode.dedicated,
        ludus_server="default",
        entry_point_vm="KALI",
    )
    orm_session.add(template)
    orm_session.flush()

    sess = Session(
        name="Spring 2026",
        start_date=datetime(2026, 4, 1, tzinfo=UTC),
        end_date=datetime(2026, 5, 1, tzinfo=UTC),
        lab_template_id=template.id,
        mode=SessionMode.dedicated,
        status=OrmSessionStatus.draft,
    )
    orm_session.add(sess)
    orm_session.flush()

    student = Student(
        session_id=sess.id,
        full_name="Alice Example",
        email="alice@example.com",
        ludus_userid="alice",
        range_id=None,
        invite_token="tok-alice",
        status=OrmStudentStatus.pending,
    )
    orm_session.add(student)
    orm_session.commit()

    # LabTemplateRead from ORM instance
    lab_dto = LabTemplateRead.model_validate(
        orm_session.execute(
            select(LabTemplate).where(LabTemplate.id == template.id)
        ).scalar_one()
    )
    assert lab_dto.id == template.id
    assert lab_dto.name == "AD Basics"
    assert lab_dto.default_mode == LabMode.dedicated
    assert lab_dto.entry_point_vm == "KALI"
    assert lab_dto.created_at is not None

    # SessionRead from ORM instance
    sess_dto = SessionRead.model_validate(
        orm_session.execute(select(Session).where(Session.id == sess.id)).scalar_one()
    )
    assert sess_dto.id == sess.id
    assert sess_dto.lab_template_id == template.id
    assert sess_dto.mode == LabMode.dedicated
    assert sess_dto.status == SessionStatus.draft

    # StudentRead needs the computed invite_url supplied by the caller.
    fetched_student = orm_session.execute(
        select(Student).where(Student.id == student.id)
    ).scalar_one()
    fake_invite_url = f"http://test/invite/{fetched_student.invite_token}"
    student_dto = StudentRead.model_validate(
        {
            **{
                "id": fetched_student.id,
                "full_name": fetched_student.full_name,
                "email": fetched_student.email,
                "ludus_userid": fetched_student.ludus_userid,
                "range_id": fetched_student.range_id,
                "status": fetched_student.status,
                "invite_redeemed_at": fetched_student.invite_redeemed_at,
                "created_at": fetched_student.created_at,
            },
            "invite_url": fake_invite_url,
        }
    )
    assert student_dto.id == fetched_student.id
    assert student_dto.email == "alice@example.com"
    assert student_dto.status == StudentStatus.pending
    assert student_dto.invite_url == fake_invite_url
    # Security: the raw token must not leak into the read schema.
    assert "invite_token" not in student_dto.model_dump()
