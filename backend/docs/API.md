# MeetingMind AI — API Reference

Complete REST API reference for MeetingMind AI v1.0. All routes are prefixed with `/api/`.
Companion: [ARCHITECTURE.md](ARCHITECTURE.md), [DATABASE.md](DATABASE.md), [SECURITY.md](SECURITY.md).

Interactive schema is also served by drf-spectacular (OpenAPI) in the running app.

---

## Conventions

### Base URL
```
http://localhost:8000/api/
```

### Authentication
- **Scheme:** JWT (SimpleJWT). Send the access token as `Authorization: Bearer <access>`.
- **Access token lifetime:** 30 min (`JWT_ACCESS_TOKEN_LIFETIME_MIN`).
- **Refresh token lifetime:** 7 days (`JWT_REFRESH_TOKEN_LIFETIME_DAYS`); rotated and
  blacklisted on logout/rotation.
- **Default permission:** every endpoint is `IsAuthenticated` **except** the auth routes marked
  `AllowAny`. Every data endpoint is additionally **owner-scoped** — you only ever see your own
  rows.

### Request / response format
- JSON in, JSON out (uploads are `multipart/form-data`).
- **Pagination:** list endpoints use `DefaultPagination`, page size **20** (`?page=`).
- **Filtering/search/ordering:** DjangoFilterBackend + SearchFilter + OrderingFilter where noted.

### Errors
Errors pass through `apps.common.exceptions.custom_exception_handler`, producing a consistent
envelope, e.g.:
```json
{ "detail": "Not found." }
```
| Status | Meaning |
|---|---|
| 400 | Validation error (bad body / params) |
| 401 | Missing/expired/invalid token (SPA auto-refreshes and retries) |
| 403 | Authenticated but not permitted (not owner) |
| 404 | Not found **or** not owned (owner-scoping returns 404, not 403, to avoid leaking existence) |
| 409 | Conflict (e.g. cancelling a terminal job) |
| 429 | Throttled (see below) |
| 5xx | Server/processing error (structured `ProcessingError` where applicable) |

### Throttling (`ScopedRateThrottle`)
| Scope | Rate | Applies to |
|---|---|---|
| `auth` | 10/min | register, login, refresh |
| `password_reset` | 5/min | forgot/reset password |
| `upload` | 30/min | meeting upload |

### Example: authenticate then call an endpoint
```bash
# 1. Login
curl -s -X POST http://localhost:8000/api/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"…"}'
# → { "access": "…", "refresh": "…", "user": {…} }

# 2. Call an owner-scoped endpoint
curl -s http://localhost:8000/api/meetings/ \
  -H "Authorization: Bearer $ACCESS"
```

---

## Health (`/api/health/`) — no auth

| Method | Path | Purpose | Response |
|---|---|---|---|
| GET | `/api/health/` | Overall health | `{status, service, components:{database,redis,storage,workers}}` |
| GET | `/api/health/database/` | DB connectivity | `{status}` (503 if down) |
| GET | `/api/health/redis/` | Broker connectivity | `{status, broker}` |
| GET | `/api/health/storage/` | Storage backend | `{status, backend}` |
| GET | `/api/health/workers/` | Worker mode/count | `{status, mode, workers}` |

## Auth (`/api/auth/`)

| Method | Path | Auth | Purpose | Request body |
|---|---|---|---|---|
| POST | `/api/auth/register/` | AllowAny (`auth`) | Create account | `{email, password, first_name?, last_name?}` |
| POST | `/api/auth/login/` | AllowAny (`auth`) | Obtain tokens | `{email, password}` → `{access, refresh, user}` |
| POST | `/api/auth/refresh/` | AllowAny (`auth`) | Refresh access | `{refresh}` → `{access}` |
| POST | `/api/auth/logout/` | IsAuthenticated | Blacklist refresh | `{refresh?}` |
| GET | `/api/auth/profile/` | IsAuthenticated | Get profile | — |
| PATCH | `/api/auth/profile/` | IsAuthenticated | Update profile | `{first_name?, last_name?}` |
| POST | `/api/auth/change-password/` | IsAuthenticated | Change password | `{current_password, new_password}` |
| POST | `/api/auth/forgot-password/` | AllowAny (`password_reset`) | Request reset | `{email}` |
| POST | `/api/auth/reset-password/` | AllowAny (`password_reset`) | Reset with token | `{token, new_password}` |

> **Security note:** password/credential entry is a user action; the API never returns raw
> tokens for reset (only a hash is stored server-side).

## Meetings (`/api/meetings/`)

All owner-scoped (`IsAuthenticated` + `IsOwner`/`OwnsMeeting`).

### Meeting CRUD (ViewSet, basename `meeting`)
| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/api/meetings/` | List meetings | filter `processing_status,language,source,is_archived`; search `title,description` |
| GET | `/api/meetings/{id}/` | Meeting detail | includes segments/ai_outputs/logs/events |
| PATCH | `/api/meetings/{id}/` | Update metadata | `{title?,description?,language?,source?,tags?}` |
| DELETE | `/api/meetings/{id}/` | Soft-delete | |

### Upload & processing
| Method | Path | Purpose | Request |
|---|---|---|---|
| POST | `/api/meetings/upload/` | Upload audio/video (throttle `upload`) | multipart `{file, title?, description?, language?, source?, tags?, on_duplicate?}` |
| GET | `/api/meetings/{id}/status/` | Poll processing status | → `{processing_status, upload_status, duration_seconds, events, …}` |
| POST | `/api/meetings/{id}/reprocess/` | Re-queue full pipeline | |
| GET | `/api/meetings/{id}/download/` | Download original file | `?version=` (default latest) |

> `on_duplicate` ∈ `reject|replace|keep_both|ignore` (SHA-256 dedup). Uploads are validated by
> magic-byte MIME sniff, size and duration; a `validation_report` is returned.

### Transcript
| Method | Path | Purpose | Params |
|---|---|---|---|
| GET | `/api/meetings/{id}/transcript/` | Transcript + segments | |
| GET | `/api/meetings/{id}/transcript/segments/` | Segments only | |
| GET | `/api/meetings/{id}/transcript/stats/` | Word/char/segment/confidence stats | |
| GET | `/api/meetings/{id}/transcript/language/` | Detected language info | |
| GET | `/api/meetings/{id}/transcript/search/` | Search segments | `q, speaker?, start?, end?` |
| GET | `/api/meetings/{id}/transcript/download/` | Export transcript | **`?fmt=txt\|srt\|vtt\|pdf\|docx`** (uses `fmt`, not `format` — DRF reserves `format`) |
| PATCH | `/api/meetings/{id}/segments/{seg_id}/` | Edit a segment | `{text, speaker?}` |
| POST | `/api/meetings/{id}/segments/{seg_id}/restore/` | Restore one segment | |
| POST | `/api/meetings/{id}/transcript/restore/` | Restore all segments | |
| POST | `/api/meetings/{id}/retranscribe/` | Re-run STT | `{model?, language?}` |

### AI analysis
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meetings/{id}/ai/` | Latest analysis (or null) |
| GET | `/api/meetings/{id}/ai/action-items/` | Action items |
| GET | `/api/meetings/{id}/ai/decisions/` | Decisions |
| GET | `/api/meetings/{id}/ai/risks/` | Risks |
| GET | `/api/meetings/{id}/ai/keywords/` | Keywords |
| GET | `/api/meetings/{id}/ai/history/` | Analysis version history |
| POST | `/api/meetings/{id}/ai/regenerate/` | Regenerate analysis (`{model?}`) |

### Meeting Chat (conversations, basename `conversation`)
| Method | Path | Purpose | Request |
|---|---|---|---|
| GET | `/api/meetings/conversations/` | List conversations | filter `meeting`; search `title` |
| POST | `/api/meetings/conversations/` | Create conversation | `{meeting, title?}` |
| GET | `/api/meetings/conversations/{id}/` | Conversation + messages | |
| PATCH | `/api/meetings/conversations/{id}/` | Rename | `{title?}` |
| DELETE | `/api/meetings/conversations/{id}/` | Delete | |
| POST | `/api/meetings/conversations/{id}/ask/` | Ask a question | `{question}` (≤ 2000 chars) → cited answer or `found:false` |
| GET | `/api/meetings/conversations/{id}/messages/` | Messages + citations | |
| GET | `/api/meetings/chat/suggested/` | Suggested questions | |

### Dashboard
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meetings/dashboard/stats/` | Dashboard statistics |

## Jobs (`/api/jobs/`)

Owner-or-admin (`IsJobOwnerOrAdmin`).

| Method | Path | Purpose | Notes |
|---|---|---|---|
| GET | `/api/jobs/` | List jobs | order by `created_at,priority,duration_ms,status` |
| GET | `/api/jobs/{id}/` | Job detail | |
| POST | `/api/jobs/{id}/retry/` | Retry failed/cancelled job | only FAILED/CANCELED |
| POST | `/api/jobs/{id}/cancel/` | Cancel | 409 if terminal |
| POST | `/api/jobs/{id}/pause/` | Pause | |
| POST | `/api/jobs/{id}/resume/` | Resume | |
| POST | `/api/jobs/{id}/requeue/` | Requeue from scratch | |
| GET | `/api/jobs/{id}/logs/` | Job logs | |
| GET | `/api/jobs/{id}/timeline/` | Timeline (events+logs+retries) | |
| GET | `/api/jobs/metrics/` | Job metrics | |

## Knowledge Hub (`/api/knowledge/`)

All `IsAuthenticated` + owner-scoped.

### Core
| Method | Path | Purpose | Params |
|---|---|---|---|
| GET | `/api/knowledge/search/` | Org-wide search | `q` (req), `k=20` (≤50), `project?,meeting?,entity_type?,speaker?,language?,date_from?,date_to?,as_of?` |
| POST | `/api/knowledge/chat/` | Cross-meeting Q&A | `{question, project_id?, k?, filters?, as_of?}` |
| GET | `/api/knowledge/stats/` | Index statistics | |
| POST | `/api/knowledge/reindex/` | Re-index all meetings | |
| GET | `/api/knowledge/insights/` | AI insights | |
| GET | `/api/knowledge/recommendations/` | Recommendations | |
| GET | `/api/knowledge/brief/` | Executive brief | `period=weekly\|monthly` |
| GET | `/api/knowledge/digest/` | Daily digest | |
| GET | `/api/knowledge/graph/` | Knowledge graph | `project?,meeting?` |
| GET | `/api/knowledge/comparison/` | Cross-project comparison | |
| GET | `/api/knowledge/conflicts/` | Detected conflicts | |
| GET | `/api/knowledge/memory/{project_id}/` | Project memory | |
| GET | `/api/knowledge/impact/{decision_id}/` | Decision impact | |
| GET | `/api/knowledge/people-graph/` | People graph | `project?` |
| POST | `/api/knowledge/nl-query/` | Natural-language query | `{q\|query}` |

### Temporal
| Method | Path | Purpose | Params |
|---|---|---|---|
| GET | `/api/knowledge/versions/` | Version history | `limit=50` (≤200) |
| GET | `/api/knowledge/timetravel/` | State at a point in time | `as_of` (ISO, req) |
| GET | `/api/knowledge/timeline/` | Topic evolution | `topic` (req), `entity_type?` |
| GET | `/api/knowledge/events/` | Audit feed | `entity_type?,event_type?,limit=100` (≤500) |
| GET | `/api/knowledge/history/{entity_type}/{entity_id}/` | Entity version chain | |
| GET | `/api/knowledge/decision/{decision_id}/evolution/` | Decision evolution | |

### Organizational reasoning
| Method | Path | Purpose | Params |
|---|---|---|---|
| GET | `/api/knowledge/reliability/` | Topic reliability score | `topic` (req) |
| GET/POST | `/api/knowledge/consensus/` | Get / recompute consensus | |
| GET | `/api/knowledge/consensus/evolution/` | Consensus over time | `topic` (req) |
| GET | `/api/knowledge/conflicts/registry/` | Conflict registry | `status?,category?` |
| POST | `/api/knowledge/conflicts/{conflict_id}/resolve/` | Resolve conflict | `{status?, decision_id?, reason?}` |
| GET | `/api/knowledge/impact-graph/{decision_id}/` | Decision impact graph | |
| GET | `/api/knowledge/memory-score/` | Org memory score | |
| GET | `/api/knowledge/memory-score/{project_id}/` | Project memory score | |

### Executive Intelligence
| Method | Path | Purpose | Params |
|---|---|---|---|
| GET | `/api/knowledge/executive/dashboard/` | Dashboard snapshot | `refresh=1` (force rebuild) |
| POST | `/api/knowledge/executive/refresh/` | Materialise snapshot | |
| GET | `/api/knowledge/executive/health/` | Workspace health | |
| GET | `/api/knowledge/executive/score/` | Workspace score | |
| GET | `/api/knowledge/executive/analytics/` | Analytics | |
| GET | `/api/knowledge/executive/insights/` | Org insights | |
| GET | `/api/knowledge/executive/recommendations/` | List recommendations | |
| POST | `/api/knowledge/executive/recommendations/{rec_id}/status/` | Update rec status | `{status}` |
| GET | `/api/knowledge/executive/alerts/` | List alerts | `status?` |
| POST | `/api/knowledge/executive/alerts/{alert_id}/status/` | Update alert status | `{status}` |
| GET | `/api/knowledge/executive/history/` | History events | |
| GET | `/api/knowledge/executive/what-changed/` | Changes since date | `since=ISO` (def 7d) |
| GET | `/api/knowledge/executive/predictions/` | Predictions | |
| GET | `/api/knowledge/executive/trends/` | Trends | `granularity=daily\|weekly\|monthly`, `metric?` |
| GET | `/api/knowledge/executive/explain/` | Metric explanation | `metric` (req), `scope=organization\|project` |
| GET | `/api/knowledge/executive/brief/` | Executive brief | `period=week\|month` |

## Workspace (`/api/workspace/`)

Owner-scoped ViewSets (standard `list/create/retrieve/partial_update/destroy`) plus custom
actions. Resources: `workspaces`, `projects`, `milestones`, `tasks`, `issues`, `decisions`,
`risks`, `follow-ups`, `notes`, `reports`, `notifications`, `activity` (read-only), `suggestions`.

### Notable filters
- `projects`: `status, workspace` · `tasks`: `status, priority, category, project, meeting, created_by_ai`
- `issues`: `status, issue_type, severity, project, meeting` · `risks`: `status, severity, project, meeting`
- `decisions`: `status, project, meeting` (search `decision, reason`) · `reports`: `report_type, project, meeting, is_current`

### Custom actions
| Method | Path | Purpose | Request |
|---|---|---|---|
| GET | `/api/workspace/tasks/board/` | Kanban board grouped by status | |
| PATCH/POST | `/api/workspace/tasks/{id}/move/` | Move card | `{status, order?}` |
| GET | `/api/workspace/tasks/{id}/related/` | Related meeting/segment/decisions/risks/issues/reports | |
| GET/POST | `/api/workspace/tasks/{id}/comments/` | List/add comment | `{body}` |
| GET | `/api/workspace/tasks/{id}/activity/` | Task activity | |
| GET | `/api/workspace/suggestions/` | AI suggestions (no direct create) | filter `status, suggestion_type, meeting` |
| POST | `/api/workspace/suggestions/{id}/approve/` | Approve → materialise record | `{edited?, reviewer_notes?, on_duplicate?}` |
| POST | `/api/workspace/suggestions/{id}/reject/` | Reject | `{reviewer_notes?}` |
| GET | `/api/workspace/suggestions/{id}/duplicates/` | Find duplicate tasks | |
| POST | `/api/workspace/suggestions/bulk/` | Bulk action | `{ids:[], action: approve\|reject\|archive}` |
| GET | `/api/workspace/suggestions/stats/` | Approval dashboard stats | |
| POST | `/api/workspace/reports/generate/` | Generate report | `{report_type, meeting?, project?}` |
| POST | `/api/workspace/notifications/{id}/read/` | Mark read | |
| POST | `/api/workspace/notifications/read-all/` | Mark all read | |

### Standalone
| Method | Path | Purpose | Params |
|---|---|---|---|
| GET | `/api/workspace/dashboard/` | Workspace dashboard | |
| GET | `/api/workspace/analytics/` | Analytics | |
| GET | `/api/workspace/search/` | Unified/semantic search | `q, semantic=1?` |
| GET | `/api/workspace/timeline/{meeting_id}/` | Meeting timeline | |

## Agents (`/api/agents/`)

### Agents
| Method | Path | Purpose | Request |
|---|---|---|---|
| GET | `/api/agents/` | List agents + tools | |
| GET | `/api/agents/matrix/` | Capability matrix | |
| POST | `/api/agents/run/` | Run one agent | `{agent, request\|input, params?, sandbox?}` |
| GET | `/api/agents/health/` | Per-agent health | |
| GET | `/api/agents/runs/` | Run history | `agent?, limit=30` (≤100) |
| GET | `/api/agents/runs/{run_id}/` | Run detail | |

### Planner
| Method | Path | Purpose | Request |
|---|---|---|---|
| POST | `/api/agents/planner/run/` | Execute multi-agent plan | `{request\|input, policy=BALANCED, params?}` |
| GET | `/api/agents/planner/runs/` | List planner runs | `limit=30` (≤100) |
| GET | `/api/agents/planner/runs/{plan_id}/` | Planner run detail | |
| POST | `/api/agents/planner/runs/{plan_id}/approve/` | Approve pending plan | (only PENDING_APPROVAL) |
| GET | `/api/agents/planner/runs/{plan_id}/graph/` | Plan execution graph | |
| GET | `/api/agents/planner/metrics/` | Planner metrics | |

> Policies: `LOWEST_LATENCY`, `FAST`, `BALANCED` (default), `HIGHEST_QUALITY`, `RESEARCH`.

### Collaboration
| Method | Path | Purpose | Request |
|---|---|---|---|
| GET | `/api/agents/collaboration/templates/` | List workflow templates | |
| POST | `/api/agents/collaboration/run/` | Execute workflow | `{request?, template?, policy=SEQUENTIAL, agents?}` |
| GET | `/api/agents/collaboration/runs/` | List runs | `limit=30` (≤100) |
| GET | `/api/agents/collaboration/runs/{collab_id}/` | Run detail | |
| POST | `/api/agents/collaboration/runs/{collab_id}/approve/` | Approve pending | (only PENDING_APPROVAL) |
| GET | `/api/agents/collaboration/runs/{collab_id}/graph/` | Workflow graph | |
| GET | `/api/agents/collaboration/metrics/` | Collaboration metrics | |

> Templates: `sprint_planning`, `executive_review`, `release_readiness`, `risk_assessment`,
> `architecture_review`, `customer_feedback`, `incident_postmortem`.

---

## Worked examples

**Upload a meeting**
```bash
curl -X POST http://localhost:8000/api/meetings/upload/ \
  -H "Authorization: Bearer $ACCESS" \
  -F "file=@standup.wav" -F "title=Daily standup" -F "language=en"
# → { "id": "…", "processing_status": "queued", "validation_report": {…} }
```

**Poll status, then read the transcript**
```bash
curl -H "Authorization: Bearer $ACCESS" http://localhost:8000/api/meetings/$ID/status/
curl -H "Authorization: Bearer $ACCESS" http://localhost:8000/api/meetings/$ID/transcript/
```

**Ask a grounded question about the meeting**
```bash
CONV=$(curl -s -X POST http://localhost:8000/api/meetings/conversations/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d "{\"meeting\":\"$ID\"}" | jq -r .id)
curl -X POST http://localhost:8000/api/meetings/conversations/$CONV/ask/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"question":"What did we decide about the payment integration?"}'
# → { "answer": "…", "citations": [{ "start_time": 8.0, … }], "found": true }
```

**Run the planner**
```bash
curl -X POST http://localhost:8000/api/agents/planner/run/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"request":"Assess release readiness for Project X","policy":"HIGHEST_QUALITY"}'
```

---

## Cross-references
- Auth & owner-scoping model → [SECURITY.md](SECURITY.md)
- Underlying entities/fields → [DATABASE.md](DATABASE.md)
- Request lifecycle → [ARCHITECTURE.md](ARCHITECTURE.md)
