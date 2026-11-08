"""AI4Bharat IndicWhisper inference using the official Vistaar checkpoints."""

import os
import shutil
import tempfile
import wave
import zipfile
from pathlib import Path
from threading import Lock

import av
import requests

from app.core.config import settings
from app.services.transcription_errors import TranscriptionProviderUnavailableError

# These archive URLs are published in the official AI4Bharat/Vistaar README.
MODEL_ARCHIVES = {
    "hi": "https://indicwhisper.objectstore.e2enetworks.net/hindi_models.zip",
    "mr": "https://indicwhisper.objectstore.e2enetworks.net/marathi_models.zip",
}
MODEL_LOCK = Lock()
INFERENCE_LOCK = Lock()
PIPELINES: dict[str, object] = {}


def _cache_root() -> Path:
    configured = (settings.indicwhisper_model_cache_dir or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".cache" / "voicedocs" / "indicwhisper").resolve()


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError("The IndicWhisper archive contains an unsafe file path.")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _find_model_directory(extraction_dir: Path, language: str) -> Path:
    expected = f"whisper-medium-{language}_"
    configs = list(extraction_dir.rglob("config.json"))
    for config in configs:
        if expected in str(config.parent).lower():
            return config.parent
    if len(configs) == 1:
        return configs[0].parent
    raise RuntimeError("Could not locate the expected IndicWhisper checkpoint in the downloaded archive.")


def _download_model(language: str) -> Path:
    language_dir = _cache_root() / language
    model_dir = language_dir / "model"
    if (model_dir / "config.json").is_file():
        return model_dir

    language_dir.mkdir(parents=True, exist_ok=True)
    archive_path = language_dir / "checkpoint.zip.part"
    extraction_dir = language_dir / "extracted"
    try:
        with requests.get(MODEL_ARCHIVES[language], stream=True, timeout=(30, 180)) as response:
            response.raise_for_status()
            with archive_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
        if not zipfile.is_zipfile(archive_path):
            raise RuntimeError("AI4Bharat returned an invalid IndicWhisper ZIP archive.")
        if extraction_dir.exists():
            shutil.rmtree(extraction_dir)
        extraction_dir.mkdir(parents=True)
        with zipfile.ZipFile(archive_path) as archive:
            _safe_extract(archive, extraction_dir)
        source_dir = _find_model_directory(extraction_dir, language)
        if model_dir.exists():
            shutil.rmtree(model_dir)
        shutil.copytree(source_dir, model_dir)
        if not (model_dir / "config.json").is_file():
            raise RuntimeError("IndicWhisper checkpoint extraction was incomplete.")
        return model_dir
    except (requests.RequestException, zipfile.BadZipFile, OSError) as exc:
        raise TranscriptionProviderUnavailableError(
            f"Could not download the IndicWhisper {language} checkpoint. Check internet access and disk space, then retry."
        ) from exc
    finally:
        if archive_path.exists():
            archive_path.unlink()
        if extraction_dir.exists():
            shutil.rmtree(extraction_dir, ignore_errors=True)


def _load_pipeline(language: str):
    if language not in MODEL_ARCHIVES:
        raise ValueError("IndicWhisper currently supports Hindi (hi) and Marathi (mr).")
    if language not in PIPELINES:
        with MODEL_LOCK:
            if language not in PIPELINES:
                try:
                    import torch
                    from transformers import pipeline
                except ImportError as exc:
                    raise TranscriptionProviderUnavailableError(
                        "IndicWhisper dependencies are missing. Install PyTorch and requirements-indicwhisper.txt "
                        "in the active VoiceDocs Python environment."
                    ) from exc

                model_dir = _download_model(language)
                try:
                    device = 0 if settings.indicwhisper_device.lower() == "cuda" and torch.cuda.is_available() else -1
                    asr = pipeline("automatic-speech-recognition", model=str(model_dir), device=device)
                    asr.model.config.forced_decoder_ids = asr.tokenizer.get_decoder_prompt_ids(
                        language=language, task="transcribe"
                    )
                except Exception as exc:
                    raise TranscriptionProviderUnavailableError(
                        "IndicWhisper could not load its checkpoint. Verify PyTorch/Transformers versions "
                        "and that the model archive downloaded completely."
                    ) from exc
                PIPELINES[language] = asr
    return PIPELINES[language]


def _convert_audio(source_path: str, wav_path: str) -> float:
    sample_rate = 16000
    total_samples = 0
    with av.open(source_path) as container:
        stream = next((item for item in container.streams if item.type == "audio"), None)
        if stream is None:
            raise ValueError("The uploaded file does not contain an audio stream.")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        with wave.open(wav_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for frame in container.decode(audio=stream.index):
                for converted in resampler.resample(frame):
                    data = converted.to_ndarray().tobytes()
                    wav_file.writeframesraw(data)
                    total_samples += len(data) // 2
            for converted in resampler.resample(None):
                data = converted.to_ndarray().tobytes()
                wav_file.writeframesraw(data)
                total_samples += len(data) // 2
    if not total_samples:
        raise ValueError("No decodable audio samples were found.")
    return total_samples / sample_rate


class IndicWhisperService:
    @staticmethod
    def transcribe(audio_bytes: bytes, filename: str, language: str | None = None) -> dict:
        if language not in MODEL_ARCHIVES:
            raise ValueError("Select Hindi (hi) or Marathi (mr) when using IndicWhisper.")
        suffix = Path(filename or "recording.webm").suffix.lower() or ".webm"
        if len(suffix) > 10 or not suffix.startswith("."):
            suffix = ".webm"

        source_path = wav_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as source:
                source.write(audio_bytes)
                source_path = source.name
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as target:
                wav_path = target.name
            duration = _convert_audio(source_path, wav_path)
            asr = _load_pipeline(language)
            # Pass decoded samples to Transformers instead of a filename. This avoids
            # its optional FFmpeg subprocess dependency on Windows.
            import numpy as np

            with wave.open(wav_path, "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                samples = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype=np.int16)
            if sample_rate != 16000:
                raise ValueError("Audio conversion did not produce the required 16 kHz sample rate.")
            audio_input = {
                "raw": samples.astype(np.float32) / 32768.0,
                "sampling_rate": sample_rate,
            }
            with INFERENCE_LOCK:
                output = asr(audio_input)
            transcript = str(output.get("text", "") if isinstance(output, dict) else output).strip()
            return {
                "text": transcript,
                "language": language,
                "language_probability": None,
                "duration": round(duration, 2),
                "segments": ([{"start": 0.0, "end": round(duration, 2), "text": transcript}] if transcript else []),
                "transcription_provider": "indicwhisper",
            }
        finally:
            for path in (source_path, wav_path):
                if path and os.path.exists(path):
                    os.remove(path)
