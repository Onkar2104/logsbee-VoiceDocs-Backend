"""Add recoverable deletion metadata for formatted document versions.

Revision ID: 0009_document_version_trash
Revises: 0008_legal_document_metadata
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_document_version_trash"
down_revision = "0008_legal_document_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_format_versions",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("document_format_versions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "document_format_versions",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_document_format_versions_is_deleted",
        "document_format_versions",
        ["is_deleted"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_format_versions_is_deleted", table_name="document_format_versions")
    op.drop_column("document_format_versions", "deleted_by")
    op.drop_column("document_format_versions", "deleted_at")
    op.drop_column("document_format_versions", "is_deleted")
