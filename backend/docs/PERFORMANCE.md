# MeetingMind AI — Performance Guide

Performance characteristics of MeetingMind AI v1.0 and the techniques used to keep it responsive.
Numbers below reflect the **local reference stack** (CPU Ollama `llama3.2:3b`, Faster-Whisper
`base` int8) — your hardware and model choices will shift them.

---

## 1. Where time goes

For a typical short meeting the wall-clock is dominated by the two AI stages, not by the app:

```
upload → validate → extract → normalize → STT → analysis → store → done
         (ms)        (ffmpeg) (ffmpeg)   (STT)  (LLM)      (ms)
                                          ▲▲▲    ▲▲▲▲▲
                                          the two costs that matter
```

## 2. Speech-to-Text (Faster-Whisper)

- **Throughput:** the reference `base`/int8/CPU config transcribes at roughly **~3× real-time**
  (≈20 s of audio per ~7 s of compute) in local measurement; a real speech clip transcribed
  word-accurately with high language confidence.
- **First run is slower:** the model is downloaded to `WHISPER_DOWNLOAD_ROOT` and loaded once,
  then cached in-process.
- **Tuning knobs:**
  | Setting | Effect |
  |---|---|
  | `WHISPER_MODEL_SIZE` | `tiny`/`base` = faster/lighter; `small`+ = more accurate/slower |
  | `WHISPER_COMPUTE_TYPE` | `int8` (default) is fastest on CPU; `float16` needs GPU |
  | `WHISPER_DEVICE` | `cuda` dramatically speeds larger models |
  | `WHISPER_BEAM_SIZE` | lower = faster, slightly less accurate |
  | `NORMALIZED_SAMPLE_RATE` | 16 kHz mono is the cheapest correct input |

## 3. LLM analysis & chat (Ollama)

- One meeting = **one grounded inference** (all artifacts in a single JSON) instead of many small
  calls — fewer round-trips, more internally consistent output.
- **Chunking** (`AI_CHUNK_SIZE=12000`, `AI_CHUNK_OVERLAP=800`) handles long transcripts via
  map-reduce with a `merge_analysis` pass; cost scales with transcript length.
- **Chat/RAG** only sends the top **`CHAT_RETRIEVAL_K=6`** retrieved segments plus
  `CHAT_HISTORY_TURNS=4` of history — small, bounded prompts keep latency low regardless of meeting
  size.
- **Tuning:** a larger Ollama model improves quality at higher latency; `AI_MAX_TOKENS`,
  `AI_TEMPERATURE`, and `AI_REQUEST_TIMEOUT` bound cost/latency. GPU-backed Ollama is the biggest
  single win.

## 4. Planner & agent latency

- **Agent runs** are dominated by (a) tool calls (DB reads) and (b) one synthesis LLM call; tool
  latency and LLM latency are recorded per run for observability.
- **Planner policies** trade breadth for latency by capping the number of agents and running them
  in parallel where possible:
  | Policy | Agents | Mode | Timeout |
  |---|---|---|---|
  | `LOWEST_LATENCY` | 2 | parallel | 20 s |
  | `FAST` | 2 | parallel | 25 s |
  | `BALANCED` | 3 | merge-LLM | 40 s |
  | `HIGHEST_QUALITY` | 5 | merge-LLM | 60 s |
  | `RESEARCH` | 6 | merge-LLM | 90 s |
- **Parallel efficiency** and per-phase timings (`planning_ms`, `execution_ms`, `merge_ms`,
  `validation_ms`) are stored on each `PlannerRun`, so slow phases are visible.
- **Collaboration** reuses tool results across agents via a shared cache (`tool_reuse_pct`),
  avoiding redundant DB/LLM work in multi-agent workflows.

## 5. Dashboard & executive performance

- Executive dashboards are **materialised**: `OrganizationSnapshot`/`ProjectSnapshot` +
  `ExecutiveTrendPoint`/`ExecutiveMetricSnapshot` are precomputed, so the dashboard endpoint serves
  a stored snapshot instead of recomputing analytics per request.
- **Scope-limited rematerialisation:** a change to one project rebuilds only that project's
  snapshot + the org rollup (driven off the event bus) — not the whole workspace.
- Trend charts read from the append-only metric time series, so they render instantly.

## 6. Knowledge retrieval performance

- `KnowledgeItem` is heavily **owner-first indexed** (`(owner, entity_type)`, `(owner, is_current)`,
  `(owner, valid_from, valid_to)`, `(owner, entity_type, entity_id, -version)`, …), so current-view
  and time-travel queries stay selective as history grows.
- Embeddings are stored locally and compared with cosine similarity; retrieval is bounded by `k`
  (search `k≤50`, chat `CHAT_RETRIEVAL_K`).
- Retrievals are logged (`KnowledgeRetrieval`) with `response_time_ms` for analysis.

## 7. Backend query performance

- **N+1 avoidance:** read paths use `select_related`/`prefetch_related` at the selectors so list
  endpoints don't fan out per-row queries.
- **Indexing:** hundreds of composite indexes back the `WHERE owner = ? AND …` shape that
  dominates queries; unique constraints protect versioning invariants without extra lookups.
- **Pagination:** list endpoints page at 20 to bound payloads and query cost.
- **ORM-only:** no raw SQL to accidentally de-optimise; the single `SELECT 1` is the health probe.

## 8. Frontend performance

- **TanStack Query** caches server state and dedupes/refetches in the background; the UI shows
  **skeleton loaders** during fetches rather than blocking.
- **Route-level code splitting** (Next.js App Router, 19 routes) keeps initial bundles small.
- Light client state is **Zustand** (no heavy global store); forms validate client-side with zod.

## 9. Async throughput

- Real async runs on Celery with priority-aware queues (`default`/`media`/`ai`/`exports`/
  `notifications`/`maintenance`), `acks_late`, `reject_on_worker_lost`, and prefetch = 1 so a
  crashed worker doesn't lose or hog tasks.
- Per-task time limits (`CELERY_TASK_TIME_LIMIT=3600`, soft `3300`) bound runaway jobs.
- For dev/demo, `CELERY_TASK_ALWAYS_EAGER=True` runs inline (simpler, lower throughput).

## 10. Tuning checklist

| Goal | Lever |
|---|---|
| Faster transcription | smaller Whisper model / GPU / `int8` |
| Better analysis quality | larger Ollama model (accept higher latency) |
| Lower planner latency | `LOWEST_LATENCY`/`FAST` policy |
| More dashboard headroom | rely on snapshots; avoid forcing `?refresh=` |
| More async throughput | more/dedicated workers per queue; GPU Ollama |

---

See also: [AI_ARCHITECTURE.md](AI_ARCHITECTURE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[DATABASE.md](DATABASE.md).
