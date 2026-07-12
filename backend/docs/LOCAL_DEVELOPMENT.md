# Local Development — full stack, real infrastructure

Complete local setup for MeetingMind AI with **real** Redis, Celery, ffmpeg,
Faster-Whisper, Ollama and PostgreSQL. 100% local, no paid APIs.

See also: [REDIS_SETUP.md](REDIS_SETUP.md) · [CELERY_SETUP.md](CELERY_SETUP.md) ·
[FFMPEG_SETUP.md](FFMPEG_SETUP.md) · [OLLAMA_ACTIVATION.md](OLLAMA_ACTIVATION.md) ·
[STT_ACTIVATION.md](STT_ACTIVATION.md).

## Prerequisites (all verified working)

| Component | How | Verify |
|---|---|---|
| Python 3.12 venv | `py -3.12 -m venv backend/venv` | `venv/Scripts/python.exe --version` |
| PostgreSQL | local server, db `meetingmind` | `curl .../api/health/database/` |
| Redis (Memurai) | see REDIS_SETUP.md | `memurai-cli ping` → PONG |
| ffmpeg | portable, see FFMPEG_SETUP.md | `ffmpeg -version` |
| Faster-Whisper | `pip install -r requirements-stt.txt` | STT_ACTIVATION.md |
| Ollama | `ollama serve` + `ollama pull llama3.2:3b` + `nomic-embed-text` | `curl localhost:11434/api/tags` |
| Node 20+ | for the frontend | `node --version` |

## `backend/.env` — real-mode keys

```dotenv
DB_ENGINE=postgres  DB_NAME=meetingmind  DB_HOST=127.0.0.1  DB_PORT=5432
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
CELERY_TASK_ALWAYS_EAGER=False           # real async
AI_PROVIDER=ollama   OLLAMA_MODEL=llama3.2:3b
STT_PROVIDER=faster_whisper   WHISPER_MODEL_SIZE=base
FFMPEG_BINARY=E:\MeetingMind\tools\ffmpeg-8.1.2-essentials_build\bin\ffmpeg.exe
FFPROBE_BINARY=E:\MeetingMind\tools\ffmpeg-8.1.2-essentials_build\bin\ffprobe.exe
```

## START all services

```powershell
# 1. Redis (Memurai) — no admin
Start-Process "C:\Program Files\Memurai\memurai.exe" -ArgumentList '"C:\Program Files\Memurai\memurai.conf"' -WindowStyle Hidden

# 2. Ollama (if not already a service)
ollama serve            # separate terminal
```
```bash
cd backend
# 3. Django API
venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload
# 4. Celery worker (new terminal)
venv/Scripts/python.exe -m celery -A config worker --loglevel=info --pool=solo --queues=default,media,ai,exports,notifications,maintenance
# 5. Frontend (new terminal)
cd ../frontend && npm run dev        # or: npm run build && npx next start -p 3000
```

## VERIFY everything is running

```bash
curl http://127.0.0.1:8000/api/health/database/   # {"status":"ok"}
curl http://127.0.0.1:8000/api/health/redis/      # {"status":"ok",...}
curl http://127.0.0.1:8000/api/health/workers/    # {"status":"ok","mode":"worker",...}
curl http://localhost:11434/api/tags              # lists llama3.2:3b, nomic-embed-text
curl http://localhost:3000/login -o /dev/null -w "%{http_code}\n"  # 200
```

## STOP all services (Windows)

```powershell
# Stop web (port 8000) and frontend (port 3000)
Get-NetTCPConnection -LocalPort 8000,3000 -State Listen | %{ Stop-Process -Id $_.OwningProcess -Force }
# Stop the Celery worker (python running 'celery')
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? { $_.CommandLine -match "celery" } | %{ Stop-Process -Id $_.ProcessId -Force }
# Stop Redis (if launched as binary): Stop-Process -Name memurai -Force
```

## Run the test suite

```bash
cd backend
CELERY_TASK_ALWAYS_EAGER=True venv/Scripts/python.exe -m pytest apps
```
(Tests force mock AI/STT providers via `conftest.py` and eager Celery via the env
override — they never need Redis/Ollama/Whisper running.)

## Gotchas

- `runserver --noreload`: code/`.env` changes need a real process restart.
  Restart by killing the port then relaunching.
- Windows Celery: always `--pool=solo`.
- Editing `.env` requires restarting **both** the Django server and the worker.
- Memurai service needs admin to start; the direct-binary launch does not.
