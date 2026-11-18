"""Add recoverable trash metadata to audio recordings.

Revision ID: 0010_audio_trash_retention
Revises: 0009_document_version_trash
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_audio_trash_retention"
down_revision = "0009_document_version_trash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audio_recordings",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "audio_recordings",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "audio_recordings",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_audio_recordings_is_deleted", "audio_recordings", ["is_deleted"])


def downgrade() -> None:
    op.drop_index("ix_audio_recordings_is_deleted", table_name="audio_recordings")
    op.drop_column("audio_recordings", "deleted_by")
    op.drop_column("audio_recordings", "deleted_at")
    op.drop_column("audio_recordings", "is_deleted")
