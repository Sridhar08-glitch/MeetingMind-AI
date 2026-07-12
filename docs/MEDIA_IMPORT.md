# Universal Media Import (Phase 14)

MeetingMind AI can ingest media from many public sources — a file upload, a
YouTube/Vimeo link, a direct MP3/MP4 URL, a podcast episode, or a podcast RSS
feed (with an episode picker), individually or in batch. **Every source funnels
into the exact same Phase 6–13 pipeline** you already use for uploads. There is
**no duplicate AI logic**: a provider's only job is to acquire a local file and
call `create_upload()`.

```
Media source ─► MediaProvider.fetch() ─► local file ─► create_upload()
                                                          │  (the single source of truth)
        Audio extraction ─► Faster-Whisper ─► Translation ─► Ollama ─► Knowledge
        ─► Workspace ─► Executive ─► Agents ─► Planner ─► Collaboration
```

## Supported sources

| Provider | Handles | Backed by |
|----------|---------|-----------|
| `FileUploadProvider` | direct file upload | existing upload path |
| `PublicVideoProvider` | YouTube, Vimeo, and ~1000 public sites | `yt-dlp` (+ ffmpeg) |
| `DirectUrlProvider` | a public `.mp3/.mp4/.wav/.m4a/.webm/…` URL | stdlib `urllib` |
| `PodcastRssProvider` | a podcast / RSS feed (choose episodes) | `feedparser` |
| `BatchImportProvider` | many URLs/files at once (fan-out) | orchestration only |
| `DummyMediaProvider` | tests (`dummy://…`, no network) | — |

All processing stays **100% local** (Faster-Whisper + Ollama + ffmpeg). yt-dlp and
feedparser only *fetch* the media; they never do AI.

## Public content only

Import is restricted to **publicly accessible** media. The app does not bypass
platform restrictions, DRM, age-gates, or private/login walls — if an extractor
reports content is private/unavailable/DRM'd, the import is refused with a clear
message. Because URLs are fetched server-side, an **SSRF guard**
(`services/media_sources/guards.py`) also applies:

- only `http`/`https` schemes are allowed;
- the hostname is resolved and rejected if **any** address is private, loopback,
  link-local, or reserved (blocks internal services and cloud-metadata endpoints);
- an optional `MEDIA_IMPORT_ALLOWED_HOSTS` allow-list can further restrict hosts.

## Duplicate detection

Before spending time downloading, an import is checked against existing meetings by
**original URL → platform + platform id → podcast/RSS GUID**, and after download by
**file hash** (the existing `create_upload` check). On a match the user chooses
**Skip** (link the existing meeting), **Reprocess** (add a new version), or
**Keep both**. In a batch, a duplicate never blocks the other items.

## The import queue

Each import is an isolated `MediaImportSession` (it never appears in the Meetings
list until it finishes), with live progress through:
`pending → analyzing → downloading → downloaded → validating → importing →
processing → completed` (or `failed` / `blocked` / `cancelled`). Downloads are
**resumable** where the provider supports it (yt-dlp `continuedl`; direct URLs via
HTTP `Range`).

## Provenance

Every imported Meeting keeps `source_url` + a `source_metadata` object (type,
platform, author/channel, original URL, thumbnail, published date, license,
duration, imported-at, importer version). The meeting detail page shows this as a
**Source Information** card. The Meeting concept/UI is otherwise unchanged.

## Configuration

```
MEDIA_IMPORT_ENABLED=True                 # master switch (hides the UI tab when off)
MEDIA_IMPORT_ALLOWED_HOSTS=               # empty = any public host
MEDIA_IMPORT_MAX_DURATION_SECONDS=21600   # defaults to MAX_AUDIO_DURATION_SECONDS
MEDIA_IMPORT_TIMEOUT=60                    # network timeout for feed/direct fetches
MAX_UPLOAD_SIZE_MB=2048                    # also caps a downloaded file
```

Dependencies: `yt-dlp`, `feedparser` (both FOSS, local). yt-dlp reuses the
configured `FFMPEG_BINARY`.

## API

- `POST /api/meetings/import/analyze/` `{url|urls}` → metadata preview (+ RSS episodes)
- `POST /api/meetings/import/` `{url|urls, episode_id?, requested_media, languages…, on_duplicate}` → session(s)
- `GET  /api/meetings/import/` — the caller's recent/active import sessions
- `GET  /api/meetings/import/<id>/` — poll one session (`meeting_id` when done)
- `POST /api/meetings/import/<id>/cancel/` — cancel an in-flight import
- `GET  /api/media/sources/` — which providers are available (drives the UI)

The import runs on the Celery **`media`** queue as `meetings.run_media_import`
(registered via `apps/meetings/tasks/__init__.py`), then hands off to the normal
`meeting_processing` pipeline. **A Celery worker must be running** for imports to
process.

## Adding a new source (extensibility)

The registry (`services/media_sources/registry.py`) is the single extension point.
A future source — Google Drive, Dropbox, OneDrive, a watched folder, S3, FTP/SFTP,
WebDAV — is:

1. a new `MediaProvider` subclass implementing `can_handle` / `analyze` / `fetch`
   (returning a local file), and
2. one `registry.register(MyProvider())` call.

Nothing in the AI pipeline changes. A provider must **never** call Whisper, Ollama,
Knowledge, Workspace, Executive, Agents, Planner, or Collaboration directly — it
acquires media and ends at `create_upload()`.
