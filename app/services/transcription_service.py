import os
import tempfile
from threading import Lock

from faster_whisper import BatchedInferencePipeline, WhisperModel

from app.core.config import settings
from app.services.indicconformer_service import IndicConformerService
from app.services.indicwhisper_service import IndicWhisperService


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
    def transcribe(
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
        provider: str | None = None,
    ) -> dict:
        selected_provider = (provider or settings.transcription_provider).strip().lower()
        if selected_provider == "indicconformer":
            return IndicConformerService.transcribe(audio_bytes, filename, language)
        if selected_provider == "indicwhisper":
            return IndicWhisperService.transcribe(audio_bytes, filename, language)
        if selected_provider != "whisper":
            raise ValueError("Unsupported transcription provider. Choose whisper, indicconformer, or indicwhisper.")

        suffix = os.path.splitext(filename or "")[1].lower() or ".webm"
        if len(suffix) > 10 or not suffix.startswith("."):
            suffix = ".webm"
        auto_detect = not language
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
                vad_parameters={"min_silence_duration_ms": 800, "speech_pad_ms": 400},
                beam_size=5,
                multilingual=auto_detect,
                language_detection_segments=3,
                language_detection_threshold=0.5,
                batch_size=settings.whisper_batch_size,
            )
            results = [
                {"start": round(segment.start, 2), "end": round(segment.end, 2), "text": segment.text.strip()}
                for segment in segments
            ]
            return {
                "text": " ".join(item["text"] for item in results).strip(),
                "language": info.language,
                "language_probability": round(info.language_probability, 4),
                "duration": round(info.duration, 2),
                "segments": results,
                "transcription_provider": "whisper",
            }
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
