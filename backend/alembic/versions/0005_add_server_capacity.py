"""add cpu/ram capacity columns to ludus_servers

Revision ID: 0005_add_server_capacity
Revises: 0004_add_session_quota
Create Date: 2026-07-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_add_server_capacity"
down_revision: str | Sequence[str] | None = "0004_add_session_quota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL = unconfigured; used by the host-capacity dashboard.
    op.add_column("ludus_servers", sa.Column("cpu_capacity", sa.Integer(), nullable=True))
    op.add_column("ludus_servers", sa.Column("ram_capacity_gb", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("ludus_servers", "ram_capacity_gb")
    op.drop_column("ludus_servers", "cpu_capacity")
