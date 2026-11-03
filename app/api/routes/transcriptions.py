from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.api.dependencies.current_user import get_current_user
from app.schemas.logsbee import LogsbeeUserContext
from app.services.transcription_service import TranscriptionService


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
    user: LogsbeeUserContext = Depends(get_current_user),
):
    if file.content_type and file.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")

    audio_bytes = file.file.read(MAX_AUDIO_SIZE + 1)
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="The uploaded audio file is empty.")
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="Audio files must be 25 MB or smaller.")

    try:
        return TranscriptionService.transcribe(audio_bytes, file.filename or "recording.webm", language)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not transcribe this audio. Please try a clearer recording.") from exc
