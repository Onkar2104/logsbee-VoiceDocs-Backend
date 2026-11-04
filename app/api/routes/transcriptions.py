import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_current_user
from app.db.session import get_db
from app.schemas.logsbee import LogsbeeUserContext
from app.services.transcription_service import TranscriptionService
from app.services.google_drive_service import GoogleDriveService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transcriptions", tags=["Transcription"])

MAX_AUDIO_SIZE = 25 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm",
    "audio/ogg",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
    "video/webm",
    "application/octet-stream",
}


@router.post("/", status_code=status.HTTP_200_OK)
def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Query(default=None, min_length=2, max_length=10),
    db: Session = Depends(get_db),
    user: LogsbeeUserContext = Depends(get_current_user),
):
    media_type = (file.content_type or "").split(";")[0].strip().lower()
    if media_type and media_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")

    audio_bytes = file.file.read(MAX_AUDIO_SIZE + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="Audio files must be 25 MB or smaller.")

    filename = file.filename or "recording.webm"
    try:
        result = TranscriptionService.transcribe(audio_bytes, filename, language)
    except Exception as exc:
        logger.exception("Audio transcription failed")
        raise HTTPException(status_code=422, detail="Could not transcribe this audio. Please try a clearer recording.") from exc

    # Google Drive backup is best-effort. A Drive error must not discard a transcript.
    result["drive_saved"] = False
    result["drive_recording"] = None
    try:
        saved = GoogleDriveService.upload_recording(
            db=db,
            user_id=user.id,
            audio=audio_bytes,
            filename=filename,
            mime_type=media_type or "application/octet-stream",
            duration=result.get("duration"),
            language=result.get("language"),
            transcript=result.get("text"),
        )
        result["drive_saved"] = saved is not None
        result["drive_recording"] = saved
    except Exception:
        logger.exception("Audio was transcribed but Google Drive backup failed")

    return result
