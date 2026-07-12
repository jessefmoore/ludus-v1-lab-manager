"""add 'deploying' value to student_status enum

Revision ID: 0007_add_deploying_status
Revises: 0006_add_range_removed_status
Create Date: 2026-07-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_add_deploying_status"
down_revision: str | Sequence[str] | None = "0006_add_range_removed_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # ADD VALUE must run outside the migration's transaction.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE student_status ADD VALUE IF NOT EXISTS 'deploying'")
    # SQLite stores the enum as a VARCHAR (no native type to alter); the model
    # definition already permits the new value there.


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it;
    # a no-op keeps the enum forward-compatible.
    pass
