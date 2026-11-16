"""Add versioned formatted document storage.

Revision ID: 0006_ai_document_versions
Revises: 0005_user_preferences
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_ai_document_versions"
down_revision = "0005_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_format_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("drive_file_id", sa.String(length=255), nullable=True),
        sa.Column("drive_web_view_link", sa.Text(), nullable=True),
        sa.Column("backup_status", sa.String(length=20), nullable=False, server_default="not_backed_up"),
        sa.Column("last_backup_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_format_version_number"),
    )
    op.create_index("ix_document_format_versions_document_id", "document_format_versions", ["document_id"])
    op.create_index("ix_document_format_versions_drive_file_id", "document_format_versions", ["drive_file_id"], unique=True)

    # Nullable so all existing documents remain valid and unchanged.
    op.add_column(
        "documents",
        sa.Column("active_format_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_active_format_version",
        "documents",
        "document_format_versions",
        ["active_format_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_documents_active_format_version", "documents", type_="foreignkey")
    op.drop_column("documents", "active_format_version_id")
    op.drop_index("ix_document_format_versions_drive_file_id", table_name="document_format_versions")
    op.drop_index("ix_document_format_versions_document_id", table_name="document_format_versions")
    op.drop_table("document_format_versions")
