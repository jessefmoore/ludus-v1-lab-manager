"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-16 22:06:27.482682

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all Phase 1 MVP tables."""
    op.create_table(
        "lab_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("range_config_yaml", sa.Text(), nullable=False),
        sa.Column(
            "default_mode",
            sa.Enum("shared", "dedicated", name="lab_template_mode"),
            nullable=False,
        ),
        sa.Column("ludus_server", sa.String(length=64), nullable=False),
        sa.Column("entry_point_vm", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lab_template_id", sa.Integer(), nullable=False),
        sa.Column(
            "mode",
            sa.Enum("shared", "dedicated", name="session_mode"),
            nullable=False,
        ),
        sa.Column("shared_range_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "provisioning", "active", "ended", name="session_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["lab_template_id"], ["lab_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("ludus_userid", sa.String(length=64), nullable=False),
        sa.Column("range_id", sa.String(length=64), nullable=True),
        sa.Column("wg_config_path", sa.String(length=512), nullable=True),
        sa.Column("invite_token", sa.String(length=64), nullable=False),
        sa.Column("invite_redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("pending", "ready", "error", name="student_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_students_invite_token"), ["invite_token"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_students_ludus_userid"), ["ludus_userid"], unique=True
        )
        batch_op.create_index(
            batch_op.f("ix_students_session_id"), ["session_id"], unique=False
        )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("student_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop all Phase 1 MVP tables in reverse FK order."""
    op.drop_table("events")

    with op.batch_alter_table("students", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_students_session_id"))
        batch_op.drop_index(batch_op.f("ix_students_ludus_userid"))
        batch_op.drop_index(batch_op.f("ix_students_invite_token"))
    op.drop_table("students")

    op.drop_table("sessions")
    op.drop_table("lab_templates")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_email"))
    op.drop_table("users")
