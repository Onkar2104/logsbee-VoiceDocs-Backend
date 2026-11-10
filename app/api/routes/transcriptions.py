import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies.current_user import get_current_user
from app.db.session import get_db
from app.schemas.logsbee import LogsbeeUserContext
from app.services.transcription_service import TranscriptionService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/transcriptions", tags=["Transcription"])
MAX_AUDIO_SIZE = 25 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg",
    "audio/mp4", "audio/aac", "audio/flac", "video/webm", "application/octet-stream",
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Audio transcription failed")
        raise HTTPException(status_code=422, detail="Could not transcribe this audio. Check the selected provider setup and try a clearer recording.") from exc

    return result
