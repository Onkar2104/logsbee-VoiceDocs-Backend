# VoiceDocs Backend

FastAPI backend for VoiceDocs.

## Local development

Keep the existing local service ports configured in your `.env`; this feature does not change the API port or URL prefix.

## Transcription providers

VoiceDocs keeps `faster-whisper` as its default transcription provider. Optional AI4Bharat IndicConformer and IndicWhisper providers are available for Hindi (`hi`) and Marathi (`mr`). Both providers use the existing authenticated `POST /api/transcriptions/` endpoint and return the same transcript response shape. The selected provider is included as `transcription_provider` in the response.

### Existing Whisper provider

```env
TRANSCRIPTION_PROVIDER=whisper
WHISPER_MODEL_SIZE=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
```

Whisper supports automatic language detection. You can continue using `language=hi` or `language=mr` to force a language.

### Optional AI4Bharat IndicConformer provider

IndicConformer requires AI4Bharat's NeMo fork. It is intentionally not added to the normal `requirements.txt`, because NeMo/PyTorch has a substantial dependency footprint and may conflict with an existing Whisper environment. Install it in a dedicated Python environment first, following AI4Bharat's official instructions:

```bash
git clone https://github.com/AI4Bharat/NeMo.git
cd NeMo
git checkout nemo-v2
bash reinstall.sh
```

Official setup and model references:
- [AI4Bharat IndicConformer repository](https://github.com/AI4Bharat/IndicConformerASR)
- [Hindi model card](https://huggingface.co/ai4bharat/indicconformer_stt_hi_hybrid_ctc_rnnt_large)
- [Marathi model card](https://huggingface.co/ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large)

**Hugging Face access is required:** these model repositories require you to sign in and accept the access conditions for each language model before downloading. Open the [Hindi model page](https://huggingface.co/ai4bharat/indicconformer_stt_hi_hybrid_ctc_rnnt_large) and [Marathi model page](https://huggingface.co/ai4bharat/indicconformer_stt_mr_hybrid_ctc_rnnt_large), sign in, and accept the repository conditions. Then authenticate the same runtime with a Hugging Face read token (for example, run `hf auth login` in that environment). Never commit the token or put it in frontend configuration.

**Windows note:** AI4Bharat's NeMo installation is Linux-oriented. For this Windows development setup, use WSL2 with Ubuntu (or a Linux machine) rather than assuming the `reinstall.sh` instructions will work in native PowerShell. Install NeMo and run Uvicorn inside the same Linux environment.

After installing AI4Bharat NeMo into the Python environment used by VoiceDocs, set:

```env
TRANSCRIPTION_PROVIDER=indicconformer
INDICCONFORMER_DEVICE=cpu
```

Restart the VoiceDocs backend. Send `language=hi` for Hindi or `language=mr` for Marathi. IndicConformer does not use Whisper-style automatic language detection in this integration, so an explicit language is required. You can also test without changing `.env` by passing `provider=indicconformer` on the transcription request. The first request downloads the selected model from Hugging Face and loads it into memory; later requests reuse the in-memory model.

IndicConformer expects 16 kHz mono WAV input. The backend converts supported uploaded audio to that format using PyAV before inference. The model response does not provide word-level timestamps or confidence, so the API returns a single full-audio segment and `language_probability: null` for this provider.

### Optional AI4Bharat IndicWhisper provider

IndicWhisper is AI4Bharat’s Whisper-medium fine-tuning trained on the Vistaar Indian-language speech datasets. This initial integration enables Hindi (`hi`) and Marathi (`mr`) while keeping the existing providers unchanged. The official Vistaar repository distributes language checkpoints as ZIP archives and demonstrates inference with a Hugging Face Transformers ASR pipeline.

Install the optional dependencies into the same Python environment used by VoiceDocs:

```powershell
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements-indicwhisper.txt
```

Configure `.env`:

```env
TRANSCRIPTION_PROVIDER=indicwhisper
INDICWHISPER_DEVICE=cpu
INDICWHISPER_MODEL_CACHE_DIR=
```

Send `language=hi` or `language=mr`. On first use, the backend downloads the matching public AI4Bharat model archive and extracts it into the cache directory (default: `~/.cache/voicedocs/indicwhisper`). Each archive is several hundred MB; allow disk space and time for the first request. No Hugging Face login is required for these public Vistaar archives.

The Whisper-medium checkpoints can be slow on a CPU. This provider converts uploaded audio to 16 kHz mono WAV and returns one full-audio segment with `language_probability: null`. Model inference has not yet been runtime-tested in this repository environment; verify it with real Hindi and Marathi recordings before enabling it for users.

Official references:
- [AI4Bharat Vistaar / IndicWhisper repository](https://github.com/AI4Bharat/vistaar)
- [AI4Bharat ASR overview](https://ai4bharat.iitm.ac.in/)

### Hardware note

CPU inference is supported but may be slow. `INDICCONFORMER_DEVICE=cpu` is the safe default for systems without a compatible NVIDIA GPU. Do not set it to `cuda` unless PyTorch, CUDA, and the GPU driver are installed and compatible. Model weights are downloaded on first use and require internet access.

### Endpoint

`POST /api/transcriptions/` (requires a Logsbee Bearer access token)

Multipart form data: `file` (required). Query parameters: `language` (optional for Whisper; required as `hi` or `mr` for IndicConformer) and `provider` (`whisper` or `indicconformer`, optional; defaults to `TRANSCRIPTION_PROVIDER`). Audio uploads are limited to 25 MB. Google Drive backup remains best-effort and is unchanged.
