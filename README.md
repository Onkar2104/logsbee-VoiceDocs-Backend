# VoiceDocs Backend

FastAPI backend for VoiceDocs.

## Local development

Keep the existing local service ports configured in your `.env`; this feature does not change the API port or URL prefix.

## Transcription providers

VoiceDocs keeps `faster-whisper` as its default transcription provider. An optional AI4Bharat IndicConformer provider is available for Hindi (`hi`) and Marathi (`mr`). Both providers use the existing authenticated `POST /api/transcriptions/` endpoint and return the same transcript response shape. The selected provider is included as `transcription_provider` in the response.

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

### Hardware note

CPU inference is supported but may be slow. `INDICCONFORMER_DEVICE=cpu` is the safe default for systems without a compatible NVIDIA GPU. Do not set it to `cuda` unless PyTorch, CUDA, and the GPU driver are installed and compatible. Model weights are downloaded on first use and require internet access.

### Endpoint

`POST /api/transcriptions/` (requires a Logsbee Bearer access token)

Multipart form data: `file` (required). Query parameters: `language` (optional for Whisper; required as `hi` or `mr` for IndicConformer) and `provider` (`whisper` or `indicconformer`, optional; defaults to `TRANSCRIPTION_PROVIDER`). Audio uploads are limited to 25 MB. Google Drive backup remains best-effort and is unchanged.


## AI document formatting

Formatting is manual: the user chooses **Format Document**. The original transcript remains in the `documents.content` column; formatted content is stored separately in `document_format_versions`. The API exposes version listing, loading, replacing, creating a new version, selecting the active version, and retrying its Google Drive backup.

The backend uses the fixed Gemini `gemini-3.8-flash` model through Google's REST API with structured JSON output. The model is intentionally fixed rather than configurable so this feature cannot silently switch to a different model. Google currently lists Gemini 3.8 Flash as free of charge on the Free tier, with usage limits; upgrading the API project to a paid tier changes the applicable billing terms. Free-tier content may be used by Google to improve its products, so avoid sending sensitive or confidential transcripts until an appropriate consent and privacy experience is added. See [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) and [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output).

Set these server-only environment variables on the backend (never in Vite/frontend variables):

```env
GEMINI_API_KEY=your_google_ai_studio_api_key
DOCUMENT_AI_TIMEOUT_SECONDS=180
```

The feature does not run formatting automatically when a document is saved. A formatting request creates a new version. Users can edit and replace the selected version or save the edited content as a new version. Original and formatted DOCX files use separate Google Drive files. VoiceDocs retains database copies when Drive backup succeeds or fails.
