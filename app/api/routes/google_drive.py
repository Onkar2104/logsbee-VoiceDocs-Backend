import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.schemas.logsbee import LogsbeeUserContext
from app.services.google_drive_service import GoogleDriveService

router = APIRouter(tags=["Google Drive"])


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


@router.get("/recordings")
def list_recordings(
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    items = GoogleDriveService.recordings(db, user.id)
    return [{
        "id": str(item.id),
        "file_name": item.file_name,
        "mime_type": item.mime_type,
        "file_size": item.file_size,
        "duration_seconds": item.duration_seconds,
        "language": item.language,
        "transcript": item.transcript,
        "created_at": item.created_at.isoformat(),
    } for item in items]


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
