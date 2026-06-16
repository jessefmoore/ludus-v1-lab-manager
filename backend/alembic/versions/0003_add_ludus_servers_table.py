"""add ludus_servers table

Revision ID: 0003_add_ludus_servers
Revises: 0002_add_cover_image
Create Date: 2026-04-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_ludus_servers"
down_revision: str | Sequence[str] | None = "0002_add_cover_image"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ludus_servers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("verify_tls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ludus_servers_name", "ludus_servers", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ludus_servers_name", table_name="ludus_servers")
    op.drop_table("ludus_servers")
