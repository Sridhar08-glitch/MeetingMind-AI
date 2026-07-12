# MeetingMind AI — Demo Mode

Demo Mode gives an evaluator a **complete, realistic product experience** built from **real
recordings run through the real pipeline** — nothing is fabricated. One command generates the demo
media, uploads each file through the exact same `create_upload → Faster-Whisper → Ollama` path a
real user's upload takes, and materialises the workspace. A one-click login and a guided tour do
the rest. Evaluators can also **upload the sample recordings themselves** from the Upload page and
watch transcription + AI happen live.

---

## What gets seeded — all real

A single demo account (`demo@meetingmind.ai`) owning the **"MeetingMind AI Demo"** workspace:

- **3 projects** — Apollo Platform, Helios CRM, Nova Mobile.
- **20 meetings** across all six types — **sprint planning, standup, sales call, customer
  interview, executive meeting, design review** — a **mix of real audio (`.wav`) and video
  (`.mp4`)** recordings, backdated over the last few weeks.
- For every meeting, produced by the **real pipeline** (not fabricated):
  - a **real transcript** from **Faster-Whisper** (`faster_whisper/base`), with per-segment
    timings and confidence;
  - a versioned **AI analysis** from **local Ollama** (`llama3.2:3b`) — summaries, minutes, action
    items, decisions, risks, issues, follow-ups, deadlines, keywords;
  - **AI suggestions** materialised from that analysis, each grounded to a transcript segment.
- **Workspace** — most suggestions are **auto-approved** onto the board (tasks, decisions, risks,
  issues, follow-ups); the **last few meetings are left in `suggestions_only` mode** so the **AI
  Approvals** queue is genuinely populated with pending items to review.
- **Knowledge Hub + Executive dashboards** — built by the real services (`index_meeting`,
  consensus, executive materialisation) fired by the pipeline's completion event, so cross-meeting
  search, consensus, health scores, trends and recommendations are genuinely computed.
- A few **real grounded chat Q&As** and **real agent runs** so those surfaces have authentic
  history.

Because every meeting is genuinely processed, the dashboard metrics (meetings processed, words
transcribed, tasks/decisions captured, processing success rate, AI response time) are all real.

> **Honest note on length:** the recordings are **concise (~0.5–2.5 min each)** so a full
> 20-meeting run stays practical (each meeting runs real Whisper + Ollama). The spoken script still
> contains the intro, decisions, action-item hand-offs, risks and follow-ups, so the transcripts
> Whisper produces are coherent and the AI extraction is meaningful. Speech is synthesised locally
> with the Windows SAPI voices — no cloud, no paid API.

## How the media is generated

`manage.py generate_demo_media` turns each scripted meeting into a real file:

1. the scripted lines are synthesised to speech with the local **Windows SAPI** engine
   (`scripts/tts_synthesize.ps1`, two voices, varied speaking rate per speaker);
2. **ffmpeg** normalises audio meetings to a 16 kHz mono `.wav`, and renders video meetings as an
   `.mp4` (a title card looped over the audio).

Files are cached under `backend/demo_media/` with a `manifest.json`; regeneration is skipped unless
you pass `--force`. `create_demo` generates them automatically on first run.

## How to seed it

Any of these produce the same result (each **resets** the demo workspace to a clean state):

```bash
# 1. Django management command (from backend/) — generates media if missing, then processes all 20
venv/Scripts/python.exe manage.py create_demo

# (optional) pre-generate / rebuild just the media files
venv/Scripts/python.exe manage.py generate_demo_media --force

# 2. Standalone script (from the repo root)
python scripts/create_demo.py

# 3. In-app — Settings → "Reset demo workspace"  (or POST /api/demo/reset/)
```

> **Requires the real local stack.** Because the demo now runs the genuine pipeline, seeding needs
> **Faster-Whisper**, **ffmpeg**, and **Ollama** (`llama3.2:3b` + `nomic-embed-text`) available
> locally — the same components a real deployment uses. A full run takes roughly **20–30 minutes**
> (real transcription + AI per meeting). Media generation additionally needs **Windows SAPI**
> (built in) for text-to-speech.

## Upload a sample yourself

The bundled recordings are also offered as **samples on the Upload page** ("Or try a sample
recording"). Pick one to load it into the normal upload form, then **Upload & process** to watch
the real pipeline transcribe and analyse it live. (Since the seeded workspace already contains all
20, you'll be offered **Keep both / Replace** — the real duplicate-detection flow.) Served at
`GET /api/demo/samples/` and `GET /api/demo/samples/<filename>/`.

## Demo login

```
email:    demo@meetingmind.ai
password: DemoPass123!
```

On the login page, **"Try the live demo"** logs in with this account in one click. The credentials
are also served (for tooling) at `GET /api/demo/info/`.

## Guided tour

On first login the app launches a **6-step guided tour**:

1. **Welcome** → the Copilot home
2. **Open a meeting** → the Meetings library
3. **Review the AI summary** → the AI Review Center
4. **Ask the AI a question** → grounded, cited chat
5. **Review action items** → the Workspace / Kanban
6. **Finish**

The tour shows once (persisted in `localStorage`), can be skipped with `Esc`, and can be
**replayed** anytime from **Settings → "Restart product tour."**

## Reset

**Settings → "Reset demo workspace"** (or `POST /api/demo/reset/`) restores the original seeded
state — ideal for repeated demonstrations. The reset endpoint is **gated to the demo account (or
staff)** so a normal user can never wipe their own data by accident.

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/demo/info/` | Public | Demo availability + credentials |
| POST | `/api/demo/reset/` | Demo account / staff | Re-seed the demo workspace |
| GET | `/api/demo/samples/` | Public | List the bundled sample recordings |
| GET | `/api/demo/samples/<filename>/` | Public | Download one sample recording |

## How it's built

- **`backend/apps/common/demo_data.py`** — the shared, import-free dataset: cast, projects, the 20
  meeting scripts, and the text-to-speech line/voice builder.
- **`backend/apps/common/demo_media.py`** + **`scripts/tts_synthesize.ps1`** — generate the real
  audio/video files (local SAPI TTS + ffmpeg); `generate_demo_media` is the management command.
- **`backend/apps/common/demo.py`** — the `DemoSeeder`: uploads each real file through
  `create_upload()` and runs the real pipeline synchronously (`execute_job`), letting the
  completion event materialise suggestions, knowledge index and executive dashboards. It briefly
  suppresses Celery auto-dispatch so each meeting can be attached to its project *before* the
  pipeline runs (so derived records are project-scoped).
- **`backend/apps/common/management/commands/create_demo.py`** — the `create_demo` command.
- **`scripts/create_demo.py`** — the standalone runner.
- **`backend/apps/common/demo_views.py`** — the reset/info + sample list/download endpoints.
- **Frontend** — the Upload page "Try a sample recording" picker (`meetings/upload/page.tsx` +
  `lib/api/demo.ts`), `store/tour.ts`, `components/tour/GuidedTour.tsx`, the Settings demo section,
  and the login "Try the live demo" button.

Nothing is fabricated — the demo data is produced by the same code path a real upload runs.
