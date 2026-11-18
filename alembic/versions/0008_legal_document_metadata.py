"""Persist optional legal document formatting metadata.

Revision ID: 0008_legal_document_metadata
Revises: 0006_ai_document_versions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_legal_document_metadata"
down_revision = "0006_ai_document_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("formatting_mode", sa.String(length=20), nullable=False, server_default="general"),
    )
    op.add_column("documents", sa.Column("jurisdiction", sa.String(length=8), nullable=True))
    op.add_column("documents", sa.Column("legal_category", sa.String(length=80), nullable=True))
    op.add_column("documents", sa.Column("document_type", sa.String(length=100), nullable=True))
    op.add_column(
        "document_format_versions",
        sa.Column("legal_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_format_versions", "legal_metadata")
    op.drop_column("documents", "document_type")
    op.drop_column("documents", "legal_category")
    op.drop_column("documents", "jurisdiction")
    op.drop_column("documents", "formatting_mode")
