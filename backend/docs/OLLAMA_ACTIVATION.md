# AI Summarization Activation Guide — local Ollama LLM

MeetingMind generates summaries, action items, decisions, risks, follow-ups,
deadlines and keywords with a **local, free** LLM via [Ollama]. The default
provider is `OllamaProvider`; `DummyLLMProvider` is used **only** for automated
tests, never in normal operation. Optional cloud providers (OpenAI/Claude) exist
but are never required. **Switching providers is configuration only — no code
changes.**

## 1. Install Ollama

- **Windows/macOS:** download from https://ollama.com/download
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`

Ollama runs a local server on `http://localhost:11434`.

## 2. Pull a model

Any of the supported local models works (configurable):

```bash
ollama pull llama3.2:3b     # default — fast, ~2 GB
# alternatives:
ollama pull gemma2:2b
ollama pull mistral
ollama pull phi3
ollama pull deepseek-r1:7b
```

Verify it's available:

```bash
curl http://localhost:11434/api/tags
```

## 3. Configure environment variables (`backend/.env`)

```dotenv
AI_PROVIDER=ollama                 # the default; local, free
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b           # must match a pulled model
AI_TEMPERATURE=0.2
AI_MAX_TOKENS=2000
AI_CHUNK_SIZE=12000                # characters per chunk (llama3.2 has a large context)
AI_CHUNK_OVERLAP=800
AI_SUMMARY_STYLE=professional
AI_REQUEST_TIMEOUT=600             # seconds (CPU inference can be slow)
```

Set `AI_PROVIDER=mock` only to force the dummy provider (what tests use).

## 4. Verify

```bash
venv/Scripts/python.exe -c "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); django.setup(); from apps.meetings.services.ai import AISummarizationService as S; print(S().provider_name, S().model_name)"
# -> ollama llama3.2:3b
```

## 5. Run an analysis

AI analysis runs automatically at the end of the meeting pipeline (right after
transcription), producing ALL artifacts in a **single structured JSON inference**.
To (re)generate on an existing transcript:

- UI: open a meeting → **AI insights** panel → **Regenerate**.
- API: `POST /api/meetings/<id>/ai/regenerate/` (optional `{"model": "mistral"}`).
- Read results: `GET /api/meetings/<id>/ai/`, `.../ai/action-items`,
  `.../ai/decisions`, `.../ai/risks`, `.../ai/keywords`, `.../ai/history`.

## Notes

- **Version history:** every generation creates a new `AIAnalysis` version;
  previous results are never overwritten.
- **JSON validation:** responses are validated/normalized and retried once; a
  persistent failure is recorded as a structured `ProcessingError` on the job.
- **GPU / bigger models:** just `ollama pull` a larger model and set
  `OLLAMA_MODEL` — no code changes. Ollama uses your GPU automatically if present.
- **Prompts** live in the versioned registry (`apps/meetings/prompts/`), not in
  service code; the prompt version is stored on every result.

[Ollama]: https://ollama.com
