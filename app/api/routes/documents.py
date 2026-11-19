import logging
import re
import uuid
from html import escape as html_escape
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import Response

from app.models.document_format_version import DocumentFormatVersion
from app.models.user_settings import UserSettings
from app.services.document_formatting_service import DocumentFormattingService, sanitize_editor_html
from app.services.google_drive_service import GoogleDriveService

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_access_token, get_current_user
from app.db.session import get_db
from app.schemas.document import (
    DocumentCreate, DocumentUpdate, DocumentResponse,
    DocumentShareCreate, DocumentShareResponse, EditRequestDecision,
)
from app.schemas.logsbee import LogsbeeUserContext
from app.services.document_service import DocumentService
from app.services.docx_converter import html_to_docx
from app.services.legal_document_catalog import get_legal_catalog, get_legal_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/legal-catalog")
def get_document_legal_catalog(user: LogsbeeUserContext = Depends(get_current_user)):
    return get_legal_catalog()


def _require_format_edit_access(db: Session, document, user):
    if DocumentService._can_manage(document, user):
        return
    from app.repositories.document_repository import DocumentRepository
    share = DocumentRepository.get_share(db, document.id, uuid.UUID(user.id))
    if share is None or share.edit_request_status != "approved":
        raise HTTPException(status_code=403, detail="Edit access has not been approved.")


def _lock_document_for_version_write(db: Session, document):
    """Serialize version-number allocation and active-version updates per document."""
    model = type(document)
    return db.query(model).filter(model.id == document.id).with_for_update().one()


@router.post("/{document_id}/export/docx")
def export_document_docx(
    document_id: uuid.UUID,
    payload: dict,
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    """Build a fresh Word-compatible DOCX package from the authorized document HTML."""
    document = DocumentService._get_visible_document(db, document_id, user)
    content_html = payload.get("content_html") if isinstance(payload, dict) else None
    if not isinstance(content_html, str):
        raise HTTPException(status_code=422, detail="Document content must be HTML text.")
    safe_html, _ = sanitize_editor_html(content_html)
    try:
        docx_bytes = html_to_docx(
            f'<h1>{html_escape(document.title)}</h1>{safe_html}',
            legal_mode=getattr(document, "formatting_mode", "general") == "legal",
        )
    except Exception as exc:
        logger.exception("DOCX export failed (exception_type=%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="The Word document could not be generated. Please try again.") from exc

    safe_name = re.sub(r'[<>:"/\\\\|?*]+', "-", document.title).strip(" .") or "VoiceDocs document"
    filename = f"{safe_name[:120]}.docx"
    from urllib.parse import quote
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=\"VoiceDocs-document.docx\"; filename*=UTF-8''{quote(filename)}",
            "Content-Length": str(len(docx_bytes)),
            "Cache-Control": "no-store",
        },
    )


@router.post("/{document_id}/format")
def format_document(document_id: uuid.UUID, payload: dict | None = None, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    source = DocumentService._with_content(db, document).content
    images = {}
    if re.search(r"</?(?:p|div|h[1-6]|ul|ol|li|br|strong|b|em|i|u|s|blockquote|a|img)\b", source, re.IGNORECASE):
        source, images = DocumentFormattingService.prepare_source_with_image_placeholders(source)
    legal_context = None
    if document.formatting_mode == "legal":
        try:
            legal_context = get_legal_context(document.jurisdiction, document.legal_category, document.document_type)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=422, detail="Select a valid India legal category and document type before formatting.") from exc
    drafting_mode = bool((payload or {}).get("drafting_mode", False)) if isinstance(payload, dict) else False
    if drafting_mode and legal_context is None:
        raise HTTPException(status_code=422, detail="Select a legal document type before using legal drafting mode.")
    structured, html = DocumentFormattingService.format_transcript(
        source, legal_context=legal_context, drafting_mode=drafting_mode
    )
    if images:
        html = DocumentFormattingService.restore_embedded_images(html, images)
    document = _lock_document_for_version_write(db, document)
    latest = db.query(DocumentFormatVersion).filter(
        DocumentFormatVersion.document_id == document.id
    ).order_by(DocumentFormatVersion.version_number.desc()).first()
    version = DocumentFormatVersion(
        document_id=document.id,
        version_number=(latest.version_number + 1) if latest else 1,
        content_json=structured,
        content_html=html,
        legal_metadata=({
            "formatting_mode": "legal",
            "drafting_mode": drafting_mode,
            **legal_context,
        } if legal_context else {"formatting_mode": "general"}),
        created_by=uuid.UUID(user.id),
    )
    db.add(version)
    db.flush()
    document.active_format_version_id = version.id
    document.updated_by = uuid.UUID(user.id)
    document.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(version)
    preferences = db.query(UserSettings).filter(UserSettings.user_id == document.owner_user_id).first()
    if preferences is None or preferences.automatic_backup_enabled:
        try:
            remote = GoogleDriveService.upload_formatted_version(db, str(document.owner_user_id), str(document.id), version.version_number, document.title, version.content_html)
            version.drive_file_id = remote.get("id")
            version.drive_web_view_link = remote.get("webViewLink")
            version.backup_status = "backed_up"
            version.last_backup_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(version)
        except HTTPException:
            db.rollback()
            version = db.query(DocumentFormatVersion).filter(DocumentFormatVersion.id == version.id).first()
    return {
        "id": version.id,
        "version_number": version.version_number,
        "content_json": version.content_json,
        "content_html": version.content_html,
        "legal_metadata": version.legal_metadata,
        "backup_status": version.backup_status,
        "created_at": version.created_at,
    }


@router.post("/{document_id}/versions")
def create_document_version(document_id: uuid.UUID, payload: dict, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    document = _lock_document_for_version_write(db, document)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Formatted content must be sent as an object.")
    content_html = payload.get("content_html")
    if not isinstance(content_html, str):
        raise HTTPException(status_code=422, detail="Formatted content must be HTML text.")
    try:
        html, plain_text = sanitize_editor_html(content_html)
    except (AttributeError, TypeError) as exc:
        # Keep document text and request bodies out of logs; this traceback records
        # only the failing code path so unexpected sanitizer errors can be diagnosed.
        logger.exception("Formatted-version sanitization failed (exception_type=%s)", type(exc).__name__)
        raise HTTPException(status_code=422, detail="Formatted content could not be validated. Please try again.") from exc
    latest = db.query(DocumentFormatVersion).filter(DocumentFormatVersion.document_id == document.id).order_by(DocumentFormatVersion.version_number.desc()).first()
    version = DocumentFormatVersion(
        document_id=document.id,
        version_number=(latest.version_number + 1) if latest else 1,
        content_json={"blocks": [{"type": "paragraph", "text": plain_text}]},
        content_html=html,
        legal_metadata=(
            {"formatting_mode": "legal", **get_legal_context(document.jurisdiction, document.legal_category, document.document_type)}
            if document.formatting_mode == "legal" else {"formatting_mode": "general"}
        ),
        created_by=uuid.UUID(user.id),
    )
    db.add(version)
    db.flush()
    document.active_format_version_id = version.id
    document.updated_by = uuid.UUID(user.id)
    document.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(version)
    preferences = db.query(UserSettings).filter(UserSettings.user_id == document.owner_user_id).first()
    if preferences is None or preferences.automatic_backup_enabled:
        try:
            remote = GoogleDriveService.upload_formatted_version(db, str(document.owner_user_id), str(document.id), version.version_number, document.title, version.content_html)
            version.drive_file_id = remote.get("id")
            version.drive_web_view_link = remote.get("webViewLink")
            version.backup_status = "backed_up"
            version.last_backup_at = datetime.now(timezone.utc)
            db.commit()
        except HTTPException:
            db.rollback()
            version = db.query(DocumentFormatVersion).filter(DocumentFormatVersion.id == version.id).first()