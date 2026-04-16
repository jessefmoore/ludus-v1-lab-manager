"""Startup helpers that shape the database before the app serves traffic."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password, verify_password
from app.models.user import User

logger = logging.getLogger(__name__)


def ensure_admin_user(db: Session, settings: Settings) -> User:
    """Guarantee exactly one instructor user is present, return it.

    Behaviour:

    * If no users exist, create one from ``settings.admin_email`` /
      ``settings.admin_password`` with ``role="instructor"``.
    * If a user with ``admin_email`` already exists, return it. We do NOT
      reset the stored hash; if the env-supplied password no longer matches
      (rotated out-of-band) we log a warning and leave the DB untouched, so
      container restarts don't clobber a rotated credential.
    * If users exist but none matches ``admin_email``, log a warning and
      return the first user row (legacy / imported data case).

    The plaintext password is never logged.
    """
    existing = db.execute(
        select(User).where(User.email == settings.admin_email)
    ).scalar_one_or_none()
    if existing is not None:
        if not verify_password(settings.admin_password, existing.password_hash):
            logger.warning(
                "Admin user %s exists but ADMIN_PASSWORD does not match the stored hash; "
                "leaving stored hash untouched.",
                settings.admin_email,
            )
        return existing

    any_user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if any_user is not None:
        logger.warning(
            "No user matches ADMIN_EMAIL=%s but the users table is non-empty; "
            "returning first existing user (id=%s) without creating a new admin.",
            settings.admin_email,
            any_user.id,
        )
        return any_user

    admin = User(
        email=settings.admin_email,
        password_hash=hash_password(settings.admin_password),
        role="instructor",
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    logger.info("Bootstrapped admin user id=%s email=%s", admin.id, admin.email)
    return admin
