import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.document import Document
from app.models.user_settings import UserSettings
from app.services.document_service import DocumentService
from app.schemas.logsbee import LogsbeeUserContext
from app.services.google_drive_service import GoogleDriveService

router = APIRouter(tags=["Google Drive"])

MAX_RECORDING_SIZE = 25 * 1024 * 1024
ALLOWED_RECORDING_TYPES = {
    "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav",
    "audio/mpeg", "audio/mp4", "audio/aac", "audio/flac",
    "video/webm", "application/octet-stream",
}


@router.get("/google-drive/connect")
def connect_google_drive(
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    return {"authorization_url": GoogleDriveService.authorization_url(db, user.id)}


@router.get("/google-drive/callback")
def google_drive_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    base_url = settings.frontend_app_url.rstrip("/")
    if error or not code or not state:
        return RedirectResponse(f"{base_url}/?google_drive=error")
    try:
        email = GoogleDriveService.complete_oauth(db, code, state)
        return RedirectResponse(f"{base_url}/?google_drive=connected&email={quote(email)}")
    except Exception:
        return RedirectResponse(f"{base_url}/?google_drive=error")


@router.get("/google-drive/status")
def google_drive_status(
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    connection = GoogleDriveService.connection(db, user.id)
    return {
        "connected": connection is not None,
        "google_email": connection.google_email if connection else None,
    }


@router.delete("/google-drive/disconnect")
def disconnect_google_drive(
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    connection = GoogleDriveService.connection(db, user.id)
    if connection:
        db.delete(connection)
        db.commit()
    return {"message": "Google Drive disconnected. Existing files remain in your Google Drive."}


@router.post("/google-drive/backup-pending")
def backup_pending_files(
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    """Resume all pending owner documents and audio when automatic backup is enabled."""
    user_uuid = GoogleDriveService._user_id(user.id)
    preferences = db.query(UserSettings).filter(UserSettings.user_id == user_uuid).first()
    if preferences is not None and not preferences.automatic_backup_enabled:
        raise HTTPException(status_code=409, detail="Automatic backup is disabled in your settings.")

    connection = GoogleDriveService.connection(db, user.id)
    if connection is None:
        raise HTTPException(status_code=409, detail="Connect Google Drive before backing up pending files.")

    pending_documents = db.query(Document).filter(
        Document.owner_user_id == user_uuid,
        Document.is_deleted.is_(False),
        Document.backup_status != "backed_up",
    ).order_by(Document.created_at.asc()).all()
    from app.models.google_drive import AudioRecording
    pending_audio = db.query(AudioRecording).filter(
        AudioRecording.user_id == user_uuid,
        AudioRecording.backup_status != "backed_up",
    ).order_by(AudioRecording.created_at.asc()).all()

    results = []
    for document in pending_documents:
        try:
            outcome = DocumentService.backup(db, document.id, user)
            results.append({"id": str(document.id), "type": "document", "status": "backed_up", "progress": 100, "details": outcome})
        except HTTPException as exc:
            results.append({"id": str(document.id), "type": "document", "status": "failed", "progress": 0, "error": exc.detail})

    for recording in pending_audio:
        try:
            outcome = GoogleDriveService.backup_recording(db, user.id, recording.id)
            results.append({"id": str(recording.id), "type": "audio", "status": "backed_up", "progress": 100, "details": outcome})
        except HTTPException as exc:
            results.append({"id": str(recording.id), "type": "audio", "status": "failed", "progress": 0, "error": exc.detail})

    return {
        "total": len(results),
        "backed_up": sum(1 for item in results if item["status"] == "backed_up"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "items": results,
    }


@router.get("/recordings")
def list_recordings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    result = GoogleDriveService.recordings(db, user.id, page, page_size)
    return {
        "items": [{
            "id": str(item.id),
            "file_name": item.file_name,
            "mime_type": item.mime_type,
            "file_size": item.file_size,
            "duration_seconds": item.duration_seconds,
            "language": item.language,
            "transcript": item.transcript,
            "backup_status": item.backup_status,
            "document_id": str(item.document_id) if item.document_id else None,
            "created_at": item.created_at.isoformat(),
        } for item in result["items"]],
        "pagination": result["pagination"],
    }


@router.post("/recordings/{recording_id}/backup")
def backup_recording(
    recording_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    return GoogleDriveService.backup_recording(db, user.id, recording_id)


@router.get("/recordings/{recording_id}/content")
def recording_content(
    recording_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    content, filename, mime_type = GoogleDriveService.download(db, user.id, recording_id)
    safe_name = filename.replace('"', "")
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.delete("/recordings/{recording_id}")
def delete_recording(
    recording_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    GoogleDriveService.delete(db, user.id, recording_id)
    return {"message": "Recording deleted from Google Drive and VoiceDocs."}



@router.post("/recordings/upload", status_code=201)
def upload_recording(
    file: UploadFile = File(...),
    duration: float | None = Query(default=None, ge=0),
    language: str | None = Query(default=None, min_length=2, max_length=10),
    transcript: str | None = Form(default=None),
    document_id: uuid.UUID | None = Form(default=None),
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    media_type = (file.content_type or "").split(";")[0].strip().lower()
    if media_type and media_type not in ALLOWED_RECORDING_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")
    audio_bytes = file.file.read(MAX_RECORDING_SIZE + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="The recording file is empty.")
    if len(audio_bytes) > MAX_RECORDING_SIZE:
        raise HTTPException(status_code=413, detail="Recording files must be 25 MB or smaller.")

    if document_id:
        linked_document = db.get(Document, document_id)
        if not linked_document or str(linked_document.owner_user_id) != user.id:
            raise HTTPException(status_code=403, detail="Audio can only be attached to a document you own.")

    filename = file.filename or "browser-recording.webm"
    user_settings = db.query(UserSettings).filter(UserSettings.user_id == GoogleDriveService._user_id(user.id)).first()
    automatic_backup = user_settings.automatic_backup_enabled if user_settings else True
    try:
        saved = GoogleDriveService.upload_recording(
            db=db, user_id=user.id, audio=audio_bytes, filename=filename,
            mime_type=media_type or "application/octet-stream",
            duration=duration, language=language, transcript=transcript,
            document_id=document_id,
        )
    except HTTPException:
        saved = None

    if not automatic_backup:
        saved = None

    if saved is None:
        from app.models.google_drive import AudioRecording
        item = AudioRecording(
            user_id=GoogleDriveService._user_id(user.id),
            document_id=document_id,
            drive_file_id=None,
            file_data=audio_bytes,
            backup_status="not_backed_up",
            file_name=filename,
            mime_type=media_type or "application/octet-stream",
            file_size=len(audio_bytes),
            duration_seconds=duration,
            language=language,
            transcript=transcript,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        saved = {"id": str(item.id), "file_name": item.file_name, "backup_status": item.backup_status}

    return {"saved": True, "recording": saved, "backup_status": saved.get("backup_status", "backed_up")}
