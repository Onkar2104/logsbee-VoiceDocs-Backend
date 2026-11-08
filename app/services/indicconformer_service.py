import os
import tempfile
import wave
from pathlib import Path
from threading import Lock

import av

from app.core.config import settings


_MODEL_LOCK = Lock()
_MODELS: dict[str, object] = {}

MODEL_IDS = {
    "hi": "ai4bharat/indicconformer_stt_hi_hybrid_ctc_rnnt_large",
    "mr": "ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large",
}


def _load_model(language: str):
    if language not in MODEL_IDS:
        raise ValueError("IndicConformer currently supports the hi and mr language codes in this integration.")
    if language not in _MODELS:
        with _MODEL_LOCK:
            if language not in _MODELS:
                try:
                    import nemo.collections.asr as nemo_asr
                except ImportError as exc:
                    raise RuntimeError(
                        "IndicConformer is not installed. Follow the optional installation steps in README.md "
                        "and install the AI4Bharat NeMo fork in the active Python environment."
                    ) from exc
                model = nemo_asr.models.ASRModel.from_pretrained(MODEL_IDS[language])
                model.freeze()
                model = model.to(settings.indicconformer_device)
                model.cur_decoder = "ctc"
                _MODELS[language] = model
    return _MODELS[language]


def _convert_to_mono_16khz_wav(source_path: str, target_path: str) -> float:
    sample_rate = 16000
    total_samples = 0
    with av.open(source_path) as container:
        audio_stream = next((stream for stream in container.streams if stream.type == "audio"), None)
        if audio_stream is None:
            raise ValueError("The uploaded file does not contain an audio stream.")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        with wave.open(target_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for frame in container.decode(audio=audio_stream.index):
                for converted in resampler.resample(frame):
                    audio_bytes = converted.to_ndarray().tobytes()
                    wav_file.writeframesraw(audio_bytes)
                    total_samples += len(audio_bytes) // 2
            for converted in resampler.resample(None):
                audio_bytes = converted.to_ndarray().tobytes()
                wav_file.writeframesraw(audio_bytes)
                total_samples += len(audio_bytes) // 2
    if total_samples == 0:
        raise ValueError("No decodable audio samples were found in the uploaded file.")
    return total_samples / sample_rate


class IndicConformerService:
    @staticmethod
    def transcribe(audio_bytes: bytes, filename: str, language: str | None = None) -> dict:
        if language not in MODEL_IDS:
            raise ValueError("Select Hindi (hi) or Marathi (mr) when using IndicConformer.")
        suffix = Path(filename or "recording.webm").suffix.lower() or ".webm"
        if len(suffix) > 10 or not suffix.startswith("."):
            suffix = ".webm"

        source_path = None
        wav_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as source_file:
                source_file.write(audio_bytes)
                source_path = source_file.name
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as wav_file:
                wav_path = wav_file.name

            duration = _convert_to_mono_16khz_wav(source_path, wav_path)
            model = _load_model(language)
            outputs = model.transcribe([wav_path], batch_size=1, logprobs=False, language_id=language)
            raw_transcript = outputs[0] if outputs else ""
            transcript = getattr(raw_transcript, "text", raw_transcript)
            transcript = str(transcript).strip()
            return {
                "text": transcript,
                "language": language,
                "language_probability": None,
                "duration": round(duration, 2),
                "segments": ([{"start": 0.0, "end": round(duration, 2), "text": transcript}] if transcript else []),
                "transcription_provider": "indicconformer",
            }
        finally:
            for temp_path in (source_path, wav_path):
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
