"""add cpu/ram quota columns to sessions

Revision ID: 0004_add_session_quota
Revises: 0003_add_ludus_servers
Create Date: 2026-07-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_session_quota"
down_revision: str | Sequence[str] | None = "0003_add_ludus_servers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL = unlimited; enforced as a hard block at provision time.
    op.add_column("sessions", sa.Column("cpu_quota", sa.Integer(), nullable=True))
    op.add_column("sessions", sa.Column("ram_quota_gb", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "ram_quota_gb")
    op.drop_column("sessions", "cpu_quota")
