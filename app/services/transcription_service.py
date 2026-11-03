import os
import tempfile
from threading import Lock

from faster_whisper import BatchedInferencePipeline, WhisperModel

from app.core.config import settings


_model_lock = Lock()
_pipeline_lock = Lock()
_model: WhisperModel | None = None
_pipeline: BatchedInferencePipeline | None = None


def get_whisper_model() -> WhisperModel:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = WhisperModel(
                    settings.whisper_model_size,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                    cpu_threads=settings.whisper_cpu_threads,
                    num_workers=1,
                )
    return _model


def get_whisper_pipeline() -> BatchedInferencePipeline:
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = BatchedInferencePipeline(model=get_whisper_model())
    return _pipeline


class TranscriptionService:
    @staticmethod
    def transcribe(audio_bytes: bytes, filename: str, language: str | None = None) -> dict:
        suffix = os.path.splitext(filename or "")[1].lower() or ".webm"
        if len(suffix) > 10 or not suffix.startswith("."):
            suffix = ".webm"

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as audio_file:
                audio_file.write(audio_bytes)
                temp_path = audio_file.name

            segments, info = get_whisper_pipeline().transcribe(
                temp_path,
                language=language or None,
                task="transcribe",
                vad_filter=True,
                beam_size=5,
                condition_on_previous_text=True,
                batch_size=settings.whisper_batch_size,
            )
            results = [
                {
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": segment.text.strip(),
                }
                for segment in segments
            ]
            return {
                "text": " ".join(item["text"] for item in results).strip(),
                "language": info.language,
                "language_probability": round(info.language_probability, 4),
                "duration": round(info.duration, 2),
                "segments": results,
            }
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
