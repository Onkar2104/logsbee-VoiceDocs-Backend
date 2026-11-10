"""Add database fallback for documents and audio until Drive backup succeeds."""

from alembic import op
import sqlalchemy as sa

revision = "0005_database_backup_fallback"
down_revision = "0004_drive_doc_backup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_recordings", sa.Column("document_id", sa.Uuid(), nullable=True))
    op.add_column("audio_recordings", sa.Column("file_data", sa.LargeBinary(), nullable=True))
    op.add_column("audio_recordings", sa.Column("backup_status", sa.String(length=20), nullable=False, server_default="backed_up"))
    op.add_column("audio_recordings", sa.Column("last_backup_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("audio_recordings", "drive_file_id", existing_type=sa.String(length=255), nullable=True)
    op.create_index("ix_audio_recordings_document_id", "audio_recordings", ["document_id"])
    op.create_foreign_key(
        "fk_audio_recordings_document_id_documents",
        "audio_recordings", "documents", ["document_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_audio_recordings_document_id_documents", "audio_recordings", type_="foreignkey")
    op.drop_index("ix_audio_recordings_document_id", table_name="audio_recordings")
    op.alter_column("audio_recordings", "drive_file_id", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("audio_recordings", "last_backup_at")
    op.drop_column("audio_recordings", "backup_status")
    op.drop_column("audio_recordings", "file_data")
    op.drop_column("audio_recordings", "document_id")
