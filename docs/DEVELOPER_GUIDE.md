# MeetingMind AI — Developer Guide

How to work in the MeetingMind codebase: structure, conventions, and the extension points for the
things you'll most often add. Read [ARCHITECTURE.md](../backend/docs/ARCHITECTURE.md) and
[AI_ARCHITECTURE.md](../backend/docs/AI_ARCHITECTURE.md) first for the mental model.

---

## 1. Project structure

```
backend/
├── config/                 # settings.py, urls.py, celery app, asgi/wsgi
├── apps/
│   ├── common/             # BaseModel + mixins, storage, pagination, exceptions, health
│   ├── accounts/           # auth (JWT)
│   ├── jobs/               # generic job + pipeline engine, event bus
│   ├── meetings/           # upload, STT, AI analysis, chat; providers/ + prompts/
│   ├── workspace/          # tasks/issues/decisions/risks, AI suggestions, reports
│   ├── knowledge/          # bitemporal index, org search/chat, executive intelligence
│   └── agents/             # framework/, planner/, collaboration/, tools/, agents/
│   └── <app>/{api,services,selectors,models,tasks,enums}
└── requirements*.txt

frontend/
├── src/app/                # Next.js App Router: (auth) + (dashboard) route groups
├── src/components/         # UI primitives + feature components
├── src/lib/                # API client, query hooks, stores
└── docs/ACCESSIBILITY.md
```

Each backend app follows the same **clean layering** (`api → services/selectors → models`); see
ARCHITECTURE.md §2.

## 2. Local setup

```bash
# Backend (Python 3.12 only)
cd backend
py -3.12 -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-stt.txt
cp .env.example .env
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload

# Frontend
cd frontend && npm install && npm run dev
```

> **venv gotcha (Windows/Git Bash):** always call `venv/Scripts/python.exe` by path — activating
> can fall back to system Python.

> **Frontend note:** this Next.js build has breaking changes vs. older versions. Read the relevant
> guide under `frontend/node_modules/next/dist/docs/` before writing framework code (see
> `frontend/AGENTS.md`).

## 3. Coding standards

- **Layering is a rule, not a suggestion.** Views orchestrate; business logic lives in
  `services`; reads live in owner-scoped `selectors`. Don't query the ORM from a view for
  business data.
- **Owner-scope every read.** New querysets filter on `owner=request.user` (or go through a
  selector that does).
- **Models inherit `BaseModel`** (UUID + timestamps + audit + soft-delete) unless there's a
  specific reason not to. Workspace models inherit `OwnedModel`/`AISourcedModel`.
- **No raw SQL.** Use the ORM; full-text uses `SearchQuery`/`SearchVector`.
- **Logging, not prints.** Use module loggers (`logging.getLogger(__name__)`).
- **Typed, structured errors.** Raise `ProcessingError(code=…, retryable=…)` for pipeline/domain
  failures; the custom exception handler formats API errors.
- **Frontend:** TypeScript strict (no `any`), TanStack Query for server state, Zustand for light
  client state, react-hook-form + zod for forms. Keep components accessible (see ACCESSIBILITY.md).
- **Style:** the repo uses a relaxed line-length convention; `ruff` (dev-only) is available for
  linting. Match the surrounding code.

## 4. Adding a REST API endpoint

1. **Model** (if needed) in `apps/<app>/models.py` — inherit the right base; add `Meta.indexes`
   and constraints; create a migration.
2. **Selector** in `selectors.py` for reads — always owner-scoped, `select_related`/
   `prefetch_related` the traversals you serialize.
3. **Service** in `services/` for writes/business logic.
4. **Serializer** in `api/serializers.py`.
5. **View/ViewSet** in `api/views.py` — `IsAuthenticated` + an owner permission; thin, delegating
   to service/selector. Add throttle scope if it's expensive.
6. **Route** in `api/urls.py` (router for ViewSets; path for APIViews).
7. **Test** in `apps/<app>/tests/` (see §9).
8. Document it in [API.md](../backend/docs/API.md).

## 5. Adding an AI agent

Agents are **declarative** — you don't subclass. In `apps/agents/`:

1. Define an `AgentProfile` (role, allowed tools, prompt/behaviour) and register it in the
   `agent_registry` (see `apps/agents/agents/`).
2. Restrict it to the tools it needs — the `AgentPermissionEngine` enforces the allow-list.
3. If it needs data the tools don't yet expose, add a **tool** (§7) rather than reaching into the
   ORM.
4. It's automatically available via `POST /api/agents/run/`, selectable by the Planner, and usable
   in collaboration workflows.
5. Add a test asserting it runs, stays grounded, and only touches its permitted tools.

## 6. Adding a collaboration workflow

In `apps/agents/collaboration/templates.py`, define a `WorkflowTemplate` as an ordered list of
stages (`PRODUCE`/`HANDOFF`/`REVIEW`/`VOTE`/`DEBATE`/`CONSENSUS`/`HUMAN_GATE`/`MERGE`) with a
`CollaborationPolicy`. It becomes available at `GET /api/agents/collaboration/templates/` and
runnable via `POST /api/agents/collaboration/run/`.

## 7. Adding a Planner/agent tool

Tools are the **only** data-access path for agents. In `apps/agents/tools/`:

1. Add a tool (subclass the tool base / register in the tool registry) that resolves data via the
   owner-scoped `AgentContext` — never `Model.objects` directly.
2. Return structured, serializable data (it becomes evidence in the agent's answer).
3. Grant it to the profiles that should use it.

## 8. Adding an AI provider

To add e.g. a new LLM backend:

1. Implement the interface in `apps/meetings/services/llm/` (`LLMProvider.generate(...) ->
   LLMResponse`). For STT implement `SpeechToTextProvider`; for embeddings `EmbeddingProvider`.
2. Wire it into the factory (`get_llm_provider` / `get_speech_provider` /
   `get_embedding_provider`) behind a settings value (`AI_PROVIDER` etc.).
3. Preserve the **graceful fallback** contract — if the backend is unavailable, log and fall back
   rather than crashing.
4. Nothing else changes: all business code depends on the interface, not the provider.

## 9. Adding a pipeline stage / knowledge processor

- **Pipeline stage:** subclass `Stage` in the jobs pipeline, self-register with `@register_stage`,
  and add it (with its dependencies) to a `PipelineDefinition`. Stages must be **idempotent** and
  **retryable**; publish progress via the context. See ARCHITECTURE.md §4.
- **Knowledge processor:** when indexing new entity types into the Knowledge Hub, write
  `KnowledgeItem` **versions** (never update in place) and append a `KnowledgeEvent`; stamp the
  current `KnowledgeVersion`/`EmbeddingVersion`. Respect the bitemporal invariants
  (`is_current` uniqueness, `valid_from`/`valid_to`). See DATABASE.md §4.

## 10. Testing

- Backend tests live in `apps/<app>/tests/` and run with **pytest**. `conftest.py` forces
  **mock** AI providers (deterministic, offline) and isolates media.
- Run the suite with eager Celery:
  ```bash
  CELERY_TASK_ALWAYS_EAGER=True venv/Scripts/python.exe -m pytest -q
  ```
- Tests that exercise real worker threads use `@pytest.mark.django_db(transaction=True)`.
- Frontend gates: `npx tsc --noEmit`, `npm run lint`, `npm run build`.
- Full strategy: [TESTING.md](../backend/docs/TESTING.md).

## 11. Conventions checklist (before you open a PR)

- [ ] Reads are owner-scoped and eager-loaded; no N+1 introduced.
- [ ] New model inherits the right base + has indexes/constraints + a migration.
- [ ] Business logic in services, not views; agents touch data only via tools.
- [ ] Provider/pipeline additions preserve the fallback/idempotency contracts.
- [ ] Tests added and green; `tsc`/`eslint`/`build` clean on the frontend.
- [ ] API changes reflected in [API.md](../backend/docs/API.md).

---

See also: [ARCHITECTURE.md](../backend/docs/ARCHITECTURE.md) ·
[DATABASE.md](../backend/docs/DATABASE.md) · [TESTING.md](../backend/docs/TESTING.md) ·
[SECURITY.md](../backend/docs/SECURITY.md).
