"""Tests for the starter-pack lab-template seeding."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.db import Base
from app.models.lab_template import LabTemplate
from app.services.seed_templates import SEED_DIR, seed_lab_templates


def _settings(**kw) -> Settings:
    return Settings(
        app_env="testing",
        app_secret_key="unit-test-secret",
        admin_email="admin@example.com",
        admin_password="pw",
        ludus_default_url="https://ludus.test:8080",
        ludus_default_api_key="key",
        _env_file=None,
        **kw,
    )


def _db() -> OrmSession:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_seed_creates_templates() -> None:
    db = _db()
    n = seed_lab_templates(db, _settings())
    assert n >= 1
    templates = list(db.execute(select(LabTemplate)).scalars())
    names = {t.name for t in templates}
    assert "example" in names  # a known config from the pack
    # Every seeded template stores a real Ludus range config.
    for t in templates:
        assert "ludus:" in t.range_config_yaml
        assert t.ludus_server == "default"


def test_seed_is_idempotent() -> None:
    db = _db()
    first = seed_lab_templates(db, _settings())
    second = seed_lab_templates(db, _settings())  # sentinel present -> no-op
    assert second == 0
    assert len(list(db.execute(select(LabTemplate)).scalars())) == first


def test_seed_can_be_disabled() -> None:
    db = _db()
    assert seed_lab_templates(db, _settings(seed_lab_templates=False)) == 0
    assert list(db.execute(select(LabTemplate)).scalars()) == []


def test_seed_dir_has_configs() -> None:
    # All bundled files are valid Ludus range configs.
    files = list(SEED_DIR.glob("*.yml"))
    assert len(files) >= 20
    for f in files:
        assert "ludus:" in f.read_text(encoding="utf-8")
