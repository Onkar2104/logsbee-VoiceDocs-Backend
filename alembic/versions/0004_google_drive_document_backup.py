"""Add Google Drive document backup metadata and preferences."""

from alembic import op
import sqlalchemy as sa

revision = "0004_drive_doc_backup"
down_revision = "0003_google_drive_recordings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep document content in the database for now. The Drive migration/sync
    # service will populate these fields before content storage is changed.
    op.add_column(
        "documents",
        sa.Column("drive_file_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("drive_web_view_link", sa.Text(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "backup_status",
            sa.String(length=20),
            nullable=False,
            server_default="not_backed_up",
        ),
    )
    op.add_column(
        "documents",
        sa.Column("last_backup_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_documents_drive_file_id",
        "documents",
        ["drive_file_id"],
        unique=True,
    )

    op.add_column(
        "google_drive_connections",
        sa.Column("documents_folder_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "google_drive_connections",
        sa.Column(
            "auto_backup_documents",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("google_drive_connections", "auto_backup_documents")
    op.drop_column("google_drive_connections", "documents_folder_id")
    op.drop_index("ix_documents_drive_file_id", table_name="documents")
    op.drop_column("documents", "last_backup_at")
    op.drop_column("documents", "backup_status")
    op.drop_column("documents", "drive_web_view_link")
    op.drop_column("documents", "drive_file_id")
