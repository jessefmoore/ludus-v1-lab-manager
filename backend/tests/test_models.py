"""Tests for SQLAlchemy ORM models: metadata shape and a round-trip on sqlite."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models import (
    Event,
    LabTemplate,
    LabTemplateMode,
    Session,
    SessionMode,
    SessionStatus,
    Student,
    StudentStatus,
    User,
)


def test_all_tables_registered_on_base_metadata() -> None:
    """Smoke: the 5 expected tables are registered on Base.metadata."""
    expected = {"users", "lab_templates", "sessions", "students", "events"}
    assert expected.issubset(set(Base.metadata.tables.keys()))


def test_models_importable_from_package() -> None:
    """The public import surface exposes the five ORM classes."""
    # Imports at module top would already have failed; re-assert identity anyway.
    assert User.__tablename__ == "users"
    assert LabTemplate.__tablename__ == "lab_templates"
    assert Session.__tablename__ == "sessions"
    assert Student.__tablename__ == "students"
    assert Event.__tablename__ == "events"


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


def test_round_trip_insert_and_fetch(orm_session: OrmSession) -> None:
    """Insert one row per model in FK order, commit, then read them back."""
    # 1. User (independent)
    user = User(
        email="instructor@example.com",
        password_hash="hashed",
        role="instructor",
    )
    orm_session.add(user)

    # 2. LabTemplate
    template = LabTemplate(
        name="AD Basics",
        description="Intro AD lab",
        range_config_yaml="ludus: []\n",
        default_mode=LabTemplateMode.dedicated,
        ludus_server="default",
        entry_point_vm="KALI",
    )
    orm_session.add(template)
    orm_session.flush()  # get template.id

    # 3. Session (FK: lab_template_id)
    sess = Session(
        name="Spring 2026 Cohort",
        start_date=datetime(2026, 4, 1, tzinfo=UTC),
        end_date=datetime(2026, 5, 1, tzinfo=UTC),
        lab_template_id=template.id,
        mode=SessionMode.dedicated,
        status=SessionStatus.draft,
    )
    orm_session.add(sess)
    orm_session.flush()  # get sess.id

    # 4. Student (FK: session_id)
    student = Student(
        session_id=sess.id,
        full_name="Alice Example",
        email="alice@example.com",
        ludus_userid="alice",
        range_id=None,
        wg_config_path=None,
        invite_token="abcd1234",
        status=StudentStatus.pending,
    )
    orm_session.add(student)
    orm_session.flush()  # get student.id

    # 5. Event (FK: session_id + student_id)
    event = Event(
        session_id=sess.id,
        student_id=student.id,
        action="student.created",
        details_json={"source": "unit-test", "ok": True},
    )
    orm_session.add(event)

    orm_session.commit()

    # Fetch back.
    fetched_user = orm_session.execute(
        select(User).where(User.email == "instructor@example.com")
    ).scalar_one()
    assert fetched_user.role == "instructor"
    assert fetched_user.created_at is not None

    fetched_template = orm_session.execute(
        select(LabTemplate).where(LabTemplate.name == "AD Basics")
    ).scalar_one()
    assert fetched_template.default_mode == LabTemplateMode.dedicated
    assert fetched_template.entry_point_vm == "KALI"

    fetched_session = orm_session.execute(
        select(Session).where(Session.name == "Spring 2026 Cohort")
    ).scalar_one()
    assert fetched_session.mode == SessionMode.dedicated
    assert fetched_session.status == SessionStatus.draft
    assert fetched_session.lab_template_id == fetched_template.id

    fetched_student = orm_session.execute(
        select(Student).where(Student.ludus_userid == "alice")
    ).scalar_one()
    assert fetched_student.status == StudentStatus.pending
    assert fetched_student.invite_token == "abcd1234"
    assert fetched_student.session_id == fetched_session.id

    fetched_event = orm_session.execute(
        select(Event).where(Event.action == "student.created")
    ).scalar_one()
    assert fetched_event.session_id == fetched_session.id
    assert fetched_event.student_id == fetched_student.id
    assert fetched_event.details_json == {"source": "unit-test", "ok": True}


def test_session_students_relationship(orm_session: OrmSession) -> None:
    """Session.students back-populates via Student.session."""
    template = LabTemplate(
        name="Rel Test",
        range_config_yaml="ludus: []\n",
        default_mode=LabTemplateMode.shared,
    )
    orm_session.add(template)
    orm_session.flush()

    sess = Session(
        name="Cohort A",
        lab_template_id=template.id,
        mode=SessionMode.shared,
        shared_range_id="RZ1",
    )
    orm_session.add(sess)
    orm_session.flush()

    s1 = Student(
        session_id=sess.id,
        full_name="Bob",
        email="bob@example.com",
        ludus_userid="bob",
        invite_token="tok-bob",
    )
    s2 = Student(
        session_id=sess.id,
        full_name="Carol",
        email="carol@example.com",
        ludus_userid="carol",
        invite_token="tok-carol",
    )
    orm_session.add_all([s1, s2])
    orm_session.commit()

    refreshed = orm_session.execute(
        select(Session).where(Session.id == sess.id)
    ).scalar_one()
    assert {s.ludus_userid for s in refreshed.students} == {"bob", "carol"}
    assert refreshed.students[0].session.id == refreshed.id
