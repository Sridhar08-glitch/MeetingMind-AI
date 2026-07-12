# MeetingMind AI — Security Guide

The security model of MeetingMind AI v1.0: authentication, authorization, data isolation, input
handling, and AI-specific safeguards. This is the canonical security reference; the earlier
[SECURITY_REVIEW.md](SECURITY_REVIEW.md) is retained as the point-in-time audit that this guide
supersedes.

---

## 1. Threat model & posture

MeetingMind is a **single-tenant-per-user, local-first** application: each user's data is isolated
by `owner`, and the AI runs on local software. The primary concerns are (a) keeping one user's
data invisible to another, (b) validating untrusted uploads, and (c) keeping AI answers grounded
(no injection-driven fabrication). For **local development** the posture is sound; the only items
to change before a hosted deployment are the standard Django production-hardening flags (§10).

## 2. Authentication (JWT)

- **SimpleJWT** access + refresh tokens. Access token 30 min, refresh 7 days (configurable).
- Tokens are sent as `Authorization: Bearer <access>` — **not** cookies — so the SPA→API channel
  is not exposed to CSRF.
- **Refresh rotation** is on, and refresh tokens are **blacklisted on logout** and after rotation.
- The frontend transparently refreshes on 401 and retries; on refresh failure the user is logged
  out.
- Passwords are hashed by Django's password hashers. **Credential entry is always a user action** —
  the API never accepts credentials from any source but the authenticating user, and password
  reset stores only a **SHA-256 hash** of the reset token (raw token never persisted).

## 3. Authorization & owner isolation

- Every API view is `IsAuthenticated` by default (DRF `DEFAULT_PERMISSION_CLASSES`).
- Every data queryset is filtered to `owner=request.user` via owner permissions (`IsOwner`,
  `OwnsMeeting`, `IsJobOwnerOrAdmin`) and owner-scoped selectors.
- **Not-owned resolves to 404, not 403**, so the API doesn't leak the existence of other users'
  records.
- Verified by tests and live: a second owner's agent/planner/collaboration/knowledge queries
  return **zero** of the first owner's rows.

## 4. Agent least-privilege

- Agents access data **only** through the **Tool Registry**; they never touch the ORM directly.
- The `AgentPermissionEngine` enforces that an agent may invoke **only** the tools declared in its
  profile.
- Every tool resolves data through the owner-scoped `AgentContext`, so an agent physically cannot
  read another owner's data.
- Every run is audited (`AgentRun`/`PlannerRun`/`CollaborationRun` + step rows), and a **sandbox**
  mode can run agents without persisting side effects.

## 5. Input validation & uploads

- **Upload validation:** magic-byte MIME sniff vs. declared extension, min/max size, max duration,
  and SHA-256 checksum (with configurable duplicate handling). Mismatched/oversized files are
  rejected with a structured `validation_report`.
- **Allowed types** are an explicit allow-list (`ALLOWED_UPLOAD_EXTENSIONS`/`..._MIME_TYPES`).
- **Request validation:** DRF serializers validate all bodies; the chat `ask` endpoint caps
  question length (≤ 2000 chars).

## 6. Storage & private media

- Files are stored under `MEDIA_ROOT/private` with **UUID filenames** in date-bucketed
  directories; the original filename is sanitised and never used as the storage path (no path
  traversal).
- Downloads are **owner-checked, streamed, and versioned** — the client never controls the storage
  path.
- Media lives **outside the web root**; the download endpoint is `IsAuthenticated` + owner-scoped.

## 7. Injection defenses

- **SQL injection:** the Django ORM parameterises all queries; full-text search uses
  `SearchQuery`/`SearchVector`. There is **no raw SQL** except a `SELECT 1` liveness probe in the
  health check (no user input).
- **XSS:** React escapes by default; there is **no `dangerouslySetInnerHTML`**. The custom Markdown
  renderer sanitises link hrefs to `http(s):`/relative only and renders text nodes.
- **CSRF:** header-based JWT means CSRF doesn't apply to SPA→API calls; `CSRF_TRUSTED_ORIGINS` and
  `CORS_ALLOWED_ORIGINS` are pinned to the frontend origin.

## 8. Rate limiting

DRF `ScopedRateThrottle` protects the sensitive/expensive endpoints:

| Scope | Rate |
|---|---|
| `auth` (register/login/refresh) | 10/min |
| `password_reset` | 5/min |
| `upload` | 30/min |

> Recommendation for hosted use: add per-endpoint throttles to the LLM-bound agent/planner/
> collaboration run endpoints to prevent local resource exhaustion.

## 9. AI safety: grounding & prompt-injection

- **Grounding:** meeting chat and agents answer **only** from retrieved evidence. If the answer
  isn't in the retrieved context, the system returns `found:false` ("couldn't find that") rather
  than inventing one.
- **Validation:** an agent `AgentValidator` scores grounding/evidence/completeness and flags
  ungrounded or empty answers.
- **Consensus over invention:** conflicting information is resolved against the consensus/conflict
  registries, never fabricated.
- **Provenance:** every AI answer is stamped with provider/model/prompt-version/knowledge-version
  and links to its evidence (`KnowledgeRetrieval`, `MessageCitation`) — so answers are auditable
  and reproducible. Transcript/document content is treated as **data**, not as instructions to the
  system.

## 10. Production hardening (before any hosted deployment)

These are **configuration**, not code defects, and are the only gate between the local posture and
a hosted one:

1. `DJANGO_DEBUG=False`, a real `DJANGO_SECRET_KEY` from env, tightened `DJANGO_ALLOWED_HOSTS`,
   and HTTPS everywhere.
2. Run Redis with authentication (`requirepass`) bound to localhost/private network.
3. Add throttles to the LLM-bound agent/planner/collaboration endpoints.
4. Review CORS/CSRF trusted origins for the real frontend domain.

See [DEPLOYMENT.md](DEPLOYMENT.md) and [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md) for the
full checklist.

## 11. Summary

| Area | Status |
|---|---|
| Authentication (JWT + blacklist) | ✅ |
| Authorization / owner isolation | ✅ (verified live: 0 cross-owner rows) |
| Agent least-privilege | ✅ |
| SQL injection | ✅ (ORM only) |
| XSS | ✅ (no raw HTML, sanitised Markdown) |
| CSRF | ✅ (header JWT, pinned origins) |
| Upload validation | ✅ (magic-byte, size, duration, checksum) |
| Path traversal / private media | ✅ (UUID names, owner-only streamed) |
| Rate limiting | ✅ (auth/reset/upload; extend for LLM endpoints) |
| AI grounding / prompt-injection | ✅ (evidence-only, validated, provenance) |
| Secrets / debug / hosts / HTTPS | ⚠️ dev defaults — set for production |

---

See also: [SECURITY_REVIEW.md](SECURITY_REVIEW.md) (audit) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[API.md](API.md).
