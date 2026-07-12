# MeetingMind AI — Testing Guide

How MeetingMind is tested, and how to run and extend the suite.

---

## 1. Overview

- **Backend:** pytest (+ pytest-django, factory_boy). The suite is **248 tests** covering
  providers, owner-scoping, the job/pipeline engine, meetings/STT/AI/chat, workspace + AI
  suggestions, the bitemporal knowledge layer, executive intelligence, and the agent/planner/
  collaboration engines.
- **Frontend:** static quality gates — `tsc --noEmit`, ESLint, and `next build` (19 routes).
  (Component/E2E tests are a planned addition — see §7.)

## 2. Running backend tests

Tests force **mock** providers via `conftest.py` and expect Celery to run inline:

```bash
cd backend
CELERY_TASK_ALWAYS_EAGER=True venv/Scripts/python.exe -m pytest -q
```

Useful variants:
```bash
# a single app
CELERY_TASK_ALWAYS_EAGER=True venv/Scripts/python.exe -m pytest apps/knowledge -q
# a single test
CELERY_TASK_ALWAYS_EAGER=True venv/Scripts/python.exe -m pytest apps/meetings/tests/test_chat.py::test_grounded_answer -q
# stop on first failure, verbose
CELERY_TASK_ALWAYS_EAGER=True venv/Scripts/python.exe -m pytest -x -vv
```

> **venv gotcha:** call `venv/Scripts/python.exe` by path (activation can fall back to system
> Python on Windows/Git Bash).

## 3. Mock vs. real providers

`conftest.py` autouse fixtures pin the environment for determinism and offline runs:

- `AI_PROVIDER = mock` → `DummyLLMProvider` (stable, structured output)
- `STT_PROVIDER = mock` → `DummySpeechProvider` (deterministic transcript, no audio needed)
- `EMBEDDING_PROVIDER = mock` → `DummyEmbeddingProvider` (hashed bag-of-words, dim 64)
- a dummy cache and an isolated `MEDIA_ROOT`

This means **tests never call Ollama, Whisper or the network** — they're fast and reproducible.

To exercise the **real** providers, run the app (not the test suite) with the real stack
configured (`AI_PROVIDER=ollama`, `STT_PROVIDER=faster_whisper`, Ollama + FFmpeg installed) and
use the smoke steps in §6. The provider **factories** are themselves unit-tested against the mock
implementations.

## 4. Async / transaction-aware tests

The pipeline normally runs in a worker. In tests it runs **eagerly** (inline). Tests that must
observe committed rows across worker threads (e.g. some planner parallel-execution paths) use:

```python
@pytest.mark.django_db(transaction=True)
def test_planner_parallel(...):
    ...
```

This is why the planner/collaboration run views are declared `non_atomic_requests` in production —
worker threads need to see committed data.

## 5. Coverage focus areas

| Area | What's asserted |
|---|---|
| **Owner-scoping** | A second owner sees **zero** of the first owner's rows across meetings/knowledge/agents/planner/collaboration. |
| **Providers** | Factories return the configured provider; graceful fallback when a library is "missing". |
| **Pipeline** | Stages run in dependency order, are idempotent, retryable, resumable; events fire. |
| **STT/AI/Chat** | Transcript stored/segmented; analysis versioned; chat answers are grounded/cited or `found:false`. |
| **Workspace** | AI suggestions require approval; approval materialises the right record; audit trail intact. |
| **Knowledge** | Versioning + bitemporal `as_of()`; events appended; consensus/conflict registries. |
| **Executive** | Snapshots materialise; scope-limited rematerialisation via the event bus. |
| **Agents/Planner/Collab** | Runs persist with steps; grounding/quality scored; approval gates. |

## 6. Smoke tests (real end-to-end)

To validate the **real** stack after an environment change, boot everything (see
[ADMIN_GUIDE](../../docs/ADMIN_GUIDE.md)) and:

1. Register/login; obtain a Bearer token.
2. `POST /api/meetings/upload/` a short speech clip.
3. Poll `GET /api/meetings/{id}/status/` until `completed`.
4. `GET /api/meetings/{id}/transcript/` — verify a real transcript.
5. `GET /api/meetings/{id}/ai/` — verify grounded summary/action items.
6. Create a conversation and `ask/` a question — verify a cited answer.
7. `POST /api/agents/planner/run/` — verify an orchestrated answer with steps.

The repository also contains developer verification scripts (e.g. `verify_*.py`, `certify_*.py`,
`seed_demo.py`) used to certify phases against the real stack — these are dev tooling, not part of
the pytest suite.

## 7. Known gaps (non-blocking)

- No frontend **component/E2E** tests yet (static gates only).
- No **axe-core** accessibility CI (manual audit — see `frontend/docs/ACCESSIBILITY.md`).
- No CI pipeline config committed; the gates above are run locally.

These are tracked as additive quality investments in the engineering audit
([ENGINEERING_AUDIT.md](ENGINEERING_AUDIT.md)).

---

See also: [DEVELOPER_GUIDE.md](../../docs/DEVELOPER_GUIDE.md) · [SECURITY.md](SECURITY.md).
