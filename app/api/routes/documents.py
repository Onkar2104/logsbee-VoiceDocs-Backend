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
from app.services.legal_document_catalog import get_legal_catalog, get_legal_context, validate_document_metadata

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


@router.post("/{document_id}/legal-draft-preflight")
def legal_draft_preflight(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    """Check for missing legal-draft intake details without generating or saving a version."""
    from app.services.legal_draft_completeness import assess_legal_draft_completeness

    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    if document.formatting_mode != "legal":
        raise HTTPException(status_code=422, detail="Legal drafting preflight requires a legal document.")
    try:
        legal_context = get_legal_context(document.jurisdiction, document.legal_category, document.document_type)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Select a valid legal category and document type first.") from exc
    source = DocumentService._with_content(db, document).content
    if re.search(r"</?(?:p|div|h[1-6]|ul|ol|li|br|strong|b|em|i|u|s|blockquote|a|img)\b", source, re.IGNORECASE):
        source, _images = DocumentFormattingService.prepare_source_with_image_placeholders(source)
    return assess_legal_draft_completeness(source, legal_context)


@router.post("/{document_id}/format")
def format_document(document_id: uuid.UUID, payload: dict | None = None, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    payload = payload if isinstance(payload, dict) else {}
    drafting_mode_value = payload.get("drafting_mode", False)
    if not isinstance(drafting_mode_value, bool):
        raise HTTPException(status_code=422, detail="The drafting_mode option must be true or false.")
    drafting_mode = drafting_mode_value
    document_mode = payload.get("document_mode", "format")
    if document_mode not in {"format", "draft"}:
        raise HTTPException(status_code=422, detail="Choose either AI drafting or formatting-only mode.")
    if drafting_mode and document_mode == "format":
        document_mode = "draft"

    metadata_keys = {"formatting_mode", "jurisdiction", "legal_category", "document_type"}
    if metadata_keys.intersection(payload):
        candidate = {
            "formatting_mode": payload.get("formatting_mode", document.formatting_mode),
            "jurisdiction": payload.get("jurisdiction", document.jurisdiction),
            "legal_category": payload.get("legal_category", document.legal_category),
            "document_type": payload.get("document_type", document.document_type),
        }
        try:
            normalized = validate_document_metadata(
                candidate["formatting_mode"], candidate["jurisdiction"],
                candidate["legal_category"], candidate["document_type"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        document.formatting_mode = normalized["formatting_mode"]
        document.jurisdiction = normalized["jurisdiction"]
        document.legal_category = normalized["legal_category"]
        document.document_type = normalized["document_type"]
        db.commit()
        db.refresh(document)

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
    if drafting_mode and legal_context is None:
        raise HTTPException(status_code=422, detail="Select a legal document type before using legal drafting mode.")
    structured, html = DocumentFormattingService.format_transcript(
        source,
        legal_context=legal_context,
        drafting_mode=drafting_mode,
        document_mode=document_mode,
        document_title=document.title,
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
            "document_mode": document_mode,
            **legal_context,
        } if legal_context else {
            "formatting_mode": "general",
            "document_mode": document_mode,
        }),
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
    return {"id": version.id, "version_number": version.version_number, "content_json": version.content_json, "content_html": version.content_html, "legal_metadata": version.legal_metadata, "backup_status": version.backup_status, "created_at": version.created_at}

@router.put("/{document_id}/versions/{version_id}")
def replace_document_version(document_id: uuid.UUID, version_id: uuid.UUID, payload: dict, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    version = db.query(DocumentFormatVersion).filter(DocumentFormatVersion.id == version_id, DocumentFormatVersion.document_id == document.id, DocumentFormatVersion.is_deleted.is_(False)).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Formatted version not found.")
    try:
        html, plain_text = sanitize_editor_html(payload.get("content_html"))
    except (AttributeError, TypeError):
        raise HTTPException(status_code=422, detail="A valid formatted document is required.")
    version.content_json = {"blocks": [{"type": "paragraph", "text": plain_text}]}
    version.content_html = html
    version.legal_metadata = (
        {"formatting_mode": "legal", **get_legal_context(document.jurisdiction, document.legal_category, document.document_type)}
        if document.formatting_mode == "legal" else {"formatting_mode": "general"}
    )
    version.updated_at = datetime.now(timezone.utc)
    version.backup_status = "not_backed_up"
    document.active_format_version_id = version.id
    document.updated_by = uuid.UUID(user.id)
    document.updated_at = datetime.now(timezone.utc)

    # Persist the user's edit before making a network request. A Drive outage
    # must never roll back the only saved copy of the formatted document.
    db.commit()
    db.refresh(version)

    preferences = db.query(UserSettings).filter(UserSettings.user_id == document.owner_user_id).first()
    if preferences is None or preferences.automatic_backup_enabled:
        try:
            if version.drive_file_id:
                remote = GoogleDriveService.update_drive_document(db, str(document.owner_user_id), version.drive_file_id, f"{document.title} - Formatted v{version.version_number}", html)
            else:
                remote = GoogleDriveService.upload_formatted_version(db, str(document.owner_user_id), str(document.id), version.version_number, document.title, html)
            version.drive_file_id = remote.get("id")
            version.drive_web_view_link = remote.get("webViewLink") or version.drive_web_view_link
            version.backup_status = "backed_up"
            version.last_backup_at = datetime.now(timezone.utc)
            db.commit()
        except HTTPException:
            db.rollback()
            version = db.query(DocumentFormatVersion).filter(
                DocumentFormatVersion.id == version_id,
                DocumentFormatVersion.document_id == document.id,
            ).first()
    db.refresh(version)
    return {"id": version.id, "version_number": version.version_number, "content_json": version.content_json, "content_html": version.content_html, "legal_metadata": version.legal_metadata, "backup_status": version.backup_status, "created_at": version.created_at, "updated_at": version.updated_at}

@router.post("/{document_id}/versions/{version_id}/backup")
def backup_document_version(document_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    if not DocumentService._can_manage(document, user):
        raise HTTPException(status_code=403, detail="Only the document owner or Account Admin can back up this formatted version.")
    version = db.query(DocumentFormatVersion).filter(DocumentFormatVersion.id == version_id, DocumentFormatVersion.document_id == document.id).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Formatted version not found.")
    try:
        if version.drive_file_id:
            remote = GoogleDriveService.update_drive_document(db, str(document.owner_user_id), version.drive_file_id, f"{document.title} - Formatted v{version.version_number}", version.content_html)
        else:
            remote = GoogleDriveService.upload_formatted_version(db, str(document.owner_user_id), str(document.id), version.version_number, document.title, version.content_html)
    except HTTPException as exc:
        raise HTTPException(status_code=502, detail="Google Drive is unavailable. The formatted version remains safely stored in VoiceDocs.") from exc
    version.drive_file_id = remote.get("id")
    version.drive_web_view_link = remote.get("webViewLink") or version.drive_web_view_link
    version.backup_status = "backed_up"
    version.last_backup_at = datetime.now(timezone.utc)
    db.commit()
    return {"backup_status": version.backup_status, "drive_web_view_link": version.drive_web_view_link}

@router.get("/{document_id}/versions")
def list_document_versions(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    versions = db.query(DocumentFormatVersion).filter(
        DocumentFormatVersion.document_id == document.id,
        DocumentFormatVersion.is_deleted.is_(False),
    ).order_by(DocumentFormatVersion.version_number.desc()).all()
    return {
        "active_version_id": document.active_format_version_id,
        "items": [{
            "id": item.id,
            "version_number": item.version_number,
            "backup_status": item.backup_status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        } for item in versions],
    }


@router.get("/{document_id}/versions/{version_id}")
def get_document_version(document_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    version = db.query(DocumentFormatVersion).filter(
        DocumentFormatVersion.id == version_id,
        DocumentFormatVersion.document_id == document.id,
        DocumentFormatVersion.is_deleted.is_(False),
    ).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Formatted version not found.")
    return {
        "id": version.id,
        "version_number": version.version_number,
        "content_json": version.content_json,
        "content_html": version.content_html,
        "legal_metadata": version.legal_metadata,
        "backup_status": version.backup_status,
        "created_at": version.created_at,
        "updated_at": version.updated_at,
    }


@router.patch("/{document_id}/active-version/{version_id}")
def set_active_document_version(document_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    version = db.query(DocumentFormatVersion).filter(
        DocumentFormatVersion.id == version_id,
        DocumentFormatVersion.document_id == document.id,
        DocumentFormatVersion.is_deleted.is_(False),
    ).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Formatted version not found.")
    document.active_format_version_id = version.id
    document.updated_by = uuid.UUID(user.id)
    document.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"active_version_id": version.id, "version_number": version.version_number}


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_document(data: DocumentCreate, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.create(db, data, user)


@router.get("/")
def list_documents(
    scope: str = Query(default="my", pattern="^(my|shared|shared_by_me)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    legal_category: str | None = Query(default=None, max_length=80),
    document_type: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
    token: str = Depends(get_access_token),
):
    return DocumentService.list_for_user(
        db, user, token, scope, page, page_size, search, legal_category, document_type
    )


@router.get("/trash")
def list_document_trash(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    return DocumentService.list_trash(db, user, page, page_size)


@router.get("/version-trash")
def list_all_deleted_document_versions(db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.list_all_deleted_versions(db, user)


@router.post("/{document_id}/restore")
def restore_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.restore_document(db, document_id, user)


@router.delete("/{document_id}/permanent")
def permanently_delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.permanently_delete_document(db, document_id, user)


@router.get("/{document_id}/version-trash")
def list_deleted_document_versions(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.list_deleted_versions(db, document_id, user)


@router.delete("/{document_id}/versions/{version_id}")
def delete_document_version(document_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.delete_version(db, document_id, version_id, user)


@router.post("/{document_id}/versions/{version_id}/restore")
def restore_document_version(document_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.restore_version(db, document_id, version_id, user)


@router.delete("/{document_id}/versions/{version_id}/permanent")
def permanently_delete_document_version(document_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.permanently_delete_version(db, document_id, version_id, user)


@router.get("/sharing-summary")
def get_sharing_summary(db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.get_sharing_summary(db, user)


@router.post("/{document_id}/backup")
def backup_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.backup(db, document_id, user)


def _document_response(db: Session, document, user) -> DocumentResponse:
    can_edit = DocumentService._can_manage(document, user)
    if not can_edit:
        from app.repositories.document_repository import DocumentRepository
        share = DocumentRepository.get_share(db, document.id, uuid.UUID(user.id))
        can_edit = bool(share and share.edit_request_status == "approved")
    response = DocumentResponse.model_validate(document)
    return response.model_copy(update={"can_edit": can_edit})


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService.get(db, document_id, user)
    return _document_response(db, document, user)


@router.put("/{document_id}", response_model=DocumentResponse)
def update_document(document_id: uuid.UUID, data: DocumentUpdate, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService.update(db, document_id, data, user)
    return _document_response(db, document, user)


@router.delete("/{document_id}")
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.delete(db, document_id, user)


@router.post("/{document_id}/shares", response_model=DocumentShareResponse, status_code=status.HTTP_201_CREATED)
def share_document(document_id: uuid.UUID, data: DocumentShareCreate, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user), token: str = Depends(get_access_token)):
    return DocumentService.share(db, document_id, data.user_id, user, token)


@router.post("/{document_id}/edit-requests", response_model=DocumentShareResponse)
def request_edit_access(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.request_edit(db, document_id, user)


@router.patch("/{document_id}/edit-requests/{target_user_id}", response_model=DocumentShareResponse)
def decide_edit_access(document_id: uuid.UUID, target_user_id: uuid.UUID, data: EditRequestDecision, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.decide_edit_request(db, document_id, target_user_id, data.decision, user)


@router.get("/{document_id}/shares", response_model=list[DocumentShareResponse])
def list_document_shares(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.list_shares(db, document_id, user)


@router.delete("/{document_id}/shares/{target_user_id}")
def revoke_document_share(document_id: uuid.UUID, target_user_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.revoke_share(db, document_id, target_user_id, user)