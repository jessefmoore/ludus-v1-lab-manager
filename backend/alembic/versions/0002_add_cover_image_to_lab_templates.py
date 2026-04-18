"""add cover_image to lab_templates

Revision ID: 0002_add_cover_image
Revises: 0001_initial
Create Date: 2026-04-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_cover_image"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lab_templates", sa.Column("cover_image", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("lab_templates", "cover_image")
