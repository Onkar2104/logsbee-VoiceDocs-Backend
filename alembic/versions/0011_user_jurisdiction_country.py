"""Add the user's default legal jurisdiction country.

Revision ID: 0011_user_jurisdiction_country
Revises: 0010_audio_trash_retention
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_user_jurisdiction_country"
down_revision = "0010_audio_trash_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("jurisdiction_country", sa.String(length=2), nullable=False, server_default="IN"),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "jurisdiction_country")
