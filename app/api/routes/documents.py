import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from app.models.document_format_version import DocumentFormatVersion
from app.models.user_settings import UserSettings
from app.services.document_formatting_service import DocumentFormattingService
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

router = APIRouter(prefix="/documents", tags=["Documents"])



def _require_format_edit_access(db: Session, document, user):
    if DocumentService._can_manage(document, user):
        return
    from app.repositories.document_repository import DocumentRepository
    share = DocumentRepository.get_share(db, document.id, uuid.UUID(user.id))
    if share is None or share.edit_request_status != "approved":
        raise HTTPException(status_code=403, detail="Edit access has not been approved.")


@router.post("/{document_id}/format")
def format_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    source = DocumentService._with_content(db, document).content
    structured, html = DocumentFormattingService.format_transcript(source)
    latest = db.query(DocumentFormatVersion).filter(
        DocumentFormatVersion.document_id == document.id
    ).order_by(DocumentFormatVersion.version_number.desc()).first()
    version = DocumentFormatVersion(
        document_id=document.id,
        version_number=(latest.version_number + 1) if latest else 1,
        content_json=structured,
        content_html=html,
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
        "backup_status": version.backup_status,
        "created_at": version.created_at,
    }


@router.post("/{document_id}/versions")
def create_document_version(document_id: uuid.UUID, payload: dict, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    try:
        html, plain_text = DocumentFormattingService.sanitize_editor_html(payload.get("content_html"))
    except (AttributeError, TypeError):
        raise HTTPException(status_code=422, detail="A valid formatted document is required.")
    latest = db.query(DocumentFormatVersion).filter(DocumentFormatVersion.document_id == document.id).order_by(DocumentFormatVersion.version_number.desc()).first()
    version = DocumentFormatVersion(document_id=document.id, version_number=(latest.version_number + 1) if latest else 1, content_json={"blocks": [{"type": "paragraph", "text": plain_text}]}, content_html=html, created_by=uuid.UUID(user.id))
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
    return {"id": version.id, "version_number": version.version_number, "content_json": version.content_json, "content_html": version.content_html, "backup_status": version.backup_status, "created_at": version.created_at}

@router.put("/{document_id}/versions/{version_id}")
def replace_document_version(document_id: uuid.UUID, version_id: uuid.UUID, payload: dict, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
    version = db.query(DocumentFormatVersion).filter(DocumentFormatVersion.id == version_id, DocumentFormatVersion.document_id == document.id).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Formatted version not found.")
    try:
        html, plain_text = DocumentFormattingService.sanitize_editor_html(payload.get("content_html"))
    except (AttributeError, TypeError):
        raise HTTPException(status_code=422, detail="A valid formatted document is required.")
    version.content_json = {"blocks": [{"type": "paragraph", "text": plain_text}]}
    version.content_html = html
    version.updated_at = datetime.now(timezone.utc)
    version.backup_status = "not_backed_up"
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
        except HTTPException:
            version.backup_status = "not_backed_up"
    document.active_format_version_id = version.id
    document.updated_by = uuid.UUID(user.id)
    document.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(version)
    return {"id": version.id, "version_number": version.version_number, "content_json": version.content_json, "content_html": version.content_html, "backup_status": version.backup_status, "created_at": version.created_at, "updated_at": version.updated_at}

@router.post("/{document_id}/versions/{version_id}/backup")
def backup_document_version(document_id: uuid.UUID, version_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    document = DocumentService._get_visible_document(db, document_id, user)
    _require_format_edit_access(db, document, user)
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
        DocumentFormatVersion.document_id == document.id
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
    ).first()
    if version is None:
        raise HTTPException(status_code=404, detail="Formatted version not found.")
    return {
        "id": version.id,
        "version_number": version.version_number,
        "content_json": version.content_json,
        "content_html": version.content_html,
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
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
    token: str = Depends(get_access_token),
):
    return DocumentService.list_for_user(db, user, token, scope, page, page_size)


@router.get("/sharing-summary")
def get_sharing_summary(db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.get_sharing_summary(db, user)


@router.post("/{document_id}/backup")
def backup_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.backup(db, document_id, user)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.get(db, document_id, user)


@router.put("/{document_id}", response_model=DocumentResponse)
def update_document(document_id: uuid.UUID, data: DocumentUpdate, db: Session = Depends(get_db), user: LogsbeeUserContext = Depends(get_current_user)):
    return DocumentService.update(db, document_id, data, user)


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
