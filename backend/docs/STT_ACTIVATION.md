# Speech-to-Text Activation Guide — real local transcription

MeetingMind transcribes **locally and for free** with [Faster-Whisper]. The
architecture defaults to the real provider (`STT_PROVIDER=faster_whisper`); the
`DummySpeechProvider` is only used for automated tests and as a temporary
fallback when Faster-Whisper isn't installed. This guide turns on real
transcription. **No application code changes are required — configuration only.**

> The project is standardized on **Python 3.12** (the Faster-Whisper stack has no
> 3.14 wheels). See the repo README.

## 1. Recommended Python version

Python **3.12**. Confirm your venv:

```bash
backend/venv/Scripts/python.exe --version   # -> Python 3.12.x
```

If you don't have a 3.12 venv yet:

```bash
cd backend
py -3.12 -m venv venv
venv/Scripts/python.exe -m pip install --upgrade pip
venv/Scripts/python.exe -m pip install -r requirements.txt
```

## 2–4. Install Faster-Whisper, CTranslate2, PyAV

All three come from a single extras file (CTranslate2 and PyAV are pulled in as
dependencies of `faster-whisper`):

```bash
cd backend
venv/Scripts/python.exe -m pip install -r requirements-stt.txt
```

Verify the native stack imports:

```bash
venv/Scripts/python.exe -c "import faster_whisper, av, ctranslate2; print(faster_whisper.__version__, av.__version__, ctranslate2.__version__)"
```

## 5. Install FFmpeg (recommended, not strictly required)

Faster-Whisper decodes and resamples audio via the bundled **PyAV/av** library,
so basic transcription works **without** a system FFmpeg. Installing the FFmpeg
CLI enables the higher-quality extraction + normalization stages (and richer
`ffprobe` media inspection):

- **Windows:** download from https://www.gyan.dev/ffmpeg/builds/ and add `bin/`
  to `PATH`, or `winget install Gyan.FFmpeg`.
- **macOS:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

If it's not on `PATH`, point to it explicitly in `.env`:

```dotenv
FFMPEG_BINARY=C:/ffmpeg/bin/ffmpeg.exe
FFPROBE_BINARY=C:/ffmpeg/bin/ffprobe.exe
```

## 6. Download models

Models download automatically on first use to `WHISPER_DOWNLOAD_ROOT`
(`backend/media/whisper-models` by default). To pre-fetch, e.g. the `base` model:

```bash
venv/Scripts/python.exe -c "from faster_whisper import WhisperModel; WhisperModel('base', download_root='media/whisper-models')"
```

Model sizes (accuracy vs. speed/RAM): `tiny` (~75 MB) · `base` (~145 MB) ·
`small` (~500 MB) · `medium` (~1.5 GB) · `large-v3` (~3 GB).

## 7. Configure environment variables (`backend/.env`)

```dotenv
STT_PROVIDER=faster_whisper        # the default; real local transcription
WHISPER_MODEL_SIZE=base            # tiny | base | small | medium | large-v3
WHISPER_DEVICE=cpu                 # cpu | cuda (GPU — see below)
WHISPER_COMPUTE_TYPE=int8          # int8 (CPU) | float16 (GPU)
WHISPER_BEAM_SIZE=5
# WHISPER_DOWNLOAD_ROOT=...        # optional custom model cache
```

**GPU** (optional, later): set `WHISPER_DEVICE=cuda` and
`WHISPER_COMPUTE_TYPE=float16` — no code change (install CUDA/cuDNN separately).

## 8. Verify installation

```bash
venv/Scripts/python.exe -c "from django.conf import settings; import django,os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup(); from apps.meetings.services.transcription import SpeechToTextService as S; print(S().provider_name)"
# -> faster_whisper
```

Health endpoints also report readiness: `GET /api/health/` (and the `/jobs`
dashboard shows worker/queue health).

## 9. Switch the provider

Already done via `.env` in step 7 (`STT_PROVIDER=faster_whisper`). To force the
dummy provider for a moment (e.g. quick UI demo), set `STT_PROVIDER=mock`.

## 10. Run a transcription smoke test

Upload a short **speech** audio clip (via the app's Upload page or the API). Then:

1. Watch the job at `/jobs/<id>` — stages `media_inspection → … → speech_to_text
   → store_transcript` run, and (with a real worker) progress updates live.
2. Open the meeting detail page — the transcript appears with real segments,
   timestamps, detected language, model, confidence and processing time.
3. Or check via API: `GET /api/meetings/<id>/transcript/`.

> A silent/tone clip yields an empty transcript (Whisper's VAD filters
> non-speech) — that's expected; use real speech to see segments.

## How graceful degradation works

- `STT_PROVIDER=faster_whisper` but the library isn't installed → the factory
  logs a warning and falls back to `DummySpeechProvider` (dev stays functional).
- FFmpeg CLI absent → extraction/normalization stages skip; Faster-Whisper
  decodes the source directly via PyAV.
- Genuine FFmpeg/codec failures surface as a structured, non-retryable
  `ProcessingError` recorded on the job (visible in the job logs/timeline).
```
[Faster-Whisper]: https://github.com/SYSTRAN/faster-whisper
```
