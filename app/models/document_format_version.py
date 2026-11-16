import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentFormatVersion(Base):
    """A separately persisted AI-formatted/editable version of a document."""

    __tablename__ = "document_format_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_format_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # Structured JSON is canonical; sanitized HTML is the editor-friendly representation.
    content_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    drive_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    drive_web_view_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    backup_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_backed_up")
    last_backup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    document: Mapped["Document"] = relationship(back_populates="format_versions")
