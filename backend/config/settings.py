"""
Django settings for MeetingMind AI.

Configuration is driven entirely by environment variables (see `.env.example`)
so the same code runs unchanged across local machines. Everything here targets
local development; production concerns (Docker, cloud, Nginx) are intentionally
out of scope per the project brief.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    CELERY_TASK_ALWAYS_EAGER=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    # daphne must precede staticfiles so its ASGI-capable runserver takes over
    # (serves WebSockets in dev). Phase 13.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "channels",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.jobs",
    "apps.meetings",
    "apps.workspace",
    "apps.knowledge",
    "apps.agents",
    "apps.benchmarks",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# --- Channels / ASGI (Phase 13 live meetings) ------------------------------
ASGI_APPLICATION = "config.asgi.application"
# Reuse the already-running Redis (Memurai) as the channel layer; tests use the
# in-memory layer. Config-only, no code change to switch.
if env.bool("CHANNELS_IN_MEMORY", default=False):
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")]},
        },
    }

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.middleware.RequestUserMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# PostgreSQL is the intended database (see the project brief). `DB_ENGINE` lets a
# developer fall back to SQLite for a zero-setup local run; production stays on
# PostgreSQL. Everything else about the schema is engine-agnostic.
DB_ENGINE = env("DB_ENGINE", default="postgres")

if DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "ATOMIC_REQUESTS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="meetingmind"),
            "USER": env("DB_USER", default="postgres"),
            "PASSWORD": env("DB_PASSWORD", default="postgres"),
            "HOST": env("DB_HOST", default="127.0.0.1"),
            "PORT": env("DB_PORT", default="5432"),
            "ATOMIC_REQUESTS": True,
        }
    }

AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Private media root — uploaded files live here and are never served directly.
PRIVATE_MEDIA_ROOT = BASE_DIR / "media" / "private"

# Active storage backend for the StorageService abstraction (apps.common.storage).
# Swap to "s3"/"azure" here once those backends are implemented — nothing in the
# domain layer needs to change.
STORAGE_BACKEND = env("STORAGE_BACKEND", default="local")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        "password_reset": "5/min",
        "upload": "30/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env.int("JWT_ACCESS_TOKEN_LIFETIME_MIN", default=30)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env.int("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MeetingMind AI API",
    "DESCRIPTION": "AI Meeting Assistant — transcription, summaries, action items and chat.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# CORS / CSRF
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000"])
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@meetingmind.local")
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:3000")

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/1")
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER")
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# --- Production-ready routing / queues / priorities ------------------------
# These take effect as-is once CELERY_TASK_ALWAYS_EAGER=False + Redis are set;
# no code changes needed (see docs/REDIS_ACTIVATION.md).
CELERY_TASK_DEFAULT_QUEUE = "default"
from kombu import Queue  # noqa: E402 — real workers need Queue objects, not dicts
CELERY_TASK_QUEUES = [
    Queue("default"),
    Queue("media"),          # audio/video/transcription-bound work
    Queue("ai"),             # LLM / summarization work
    Queue("exports"),        # PDF/DOCX generation
    Queue("notifications"),  # email / push
    Queue("maintenance"),    # cleanup / housekeeping
]
# The engine's retry layer owns retries, so the task itself must not also retry.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_DEFAULT_PRIORITY = 5
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=60 * 60)      # hard 1h
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=55 * 60)
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "priority_steps": list(range(10)),
    "queue_order_strategy": "priority",
    "visibility_timeout": 3600,
}
CELERY_RESULT_EXTENDED = True

# ---------------------------------------------------------------------------
# Application-specific settings
# ---------------------------------------------------------------------------
# --- AI summarization (local LLM, free) ------------------------------------
# Provider selection is config-only. Default is the local Ollama LLM (per the
# FOSS/local-first policy). DummyLLMProvider is used ONLY for automated tests
# (conftest forces it) — never in normal operation. Optional cloud providers
# (openai/claude) exist but are never required.
AI_PROVIDER = env("AI_PROVIDER", default="ollama")
OLLAMA_BASE_URL = env("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_MODEL = env("OLLAMA_MODEL", default="llama3.2:3b")
AI_TEMPERATURE = env.float("AI_TEMPERATURE", default=0.2)
AI_MAX_TOKENS = env.int("AI_MAX_TOKENS", default=2000)       # num_predict
AI_REQUEST_TIMEOUT = env.int("AI_REQUEST_TIMEOUT", default=600)
# Chunking (characters). llama3.2 has a large context, so most meetings fit in
# one chunk; overlap preserves context across boundaries for long transcripts.
AI_CHUNK_SIZE = env.int("AI_CHUNK_SIZE", default=12000)
AI_CHUNK_OVERLAP = env.int("AI_CHUNK_OVERLAP", default=800)
AI_SUMMARY_STYLE = env("AI_SUMMARY_STYLE", default="professional")

# Embeddings for semantic retrieval (RAG chat). Local via Ollama by default.
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER", default="ollama")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", default="nomic-embed-text")
# Chat retrieval: how many transcript segments to feed the model, and how many
# prior Q&A turns to keep as conversation memory.
CHAT_RETRIEVAL_K = env.int("CHAT_RETRIEVAL_K", default=6)
CHAT_HISTORY_TURNS = env.int("CHAT_HISTORY_TURNS", default=4)

# AI → workspace: how AI-extracted items become records (human-in-the-loop).
#   "suggestions_only" (default) → always create pending suggestions to review.
#   "auto_high"                  → auto-approve items with confidence >= threshold.
#   "always"                     → auto-approve everything (not recommended).
AI_SUGGESTION_MODE = env("AI_SUGGESTION_MODE", default="suggestions_only")
AI_AUTO_APPROVE_THRESHOLD = env.int("AI_AUTO_APPROVE_THRESHOLD", default=95)

# Translation (Phase 13). Config-selected, mirrors STT/LLM. Default = local LLM
# (Ollama). "dummy"/"mock" in tests. Never a paid API.
TRANSLATION_PROVIDER = env("TRANSLATION_PROVIDER", default="ollama")
# Optional allow-list of AI-output language codes (empty = all the model reports).
AI_SUPPORTED_LANGUAGES = env.list("AI_SUPPORTED_LANGUAGES", default=[])
# Throttled AI preview during a live recording (canonical AI always runs at finalize).
LIVE_AI_ENABLED = env.bool("LIVE_AI_ENABLED", default=True)

# Optional cloud LLM providers (never required).
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", default="claude-opus-4-8")
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
OPENAI_MODEL = env("OPENAI_MODEL", default="gpt-4o")

# --- Speech-to-Text (local, free) ------------------------------------------
# Provider selection is config-only. The DEFAULT is real local transcription
# ("faster_whisper", per the FOSS/local-first policy) — install
# requirements-stt.txt to enable it. The DummySpeechProvider is used ONLY for
# automated tests and as a temporary fallback when Faster-Whisper is not
# installed; the app never relies on it in normal use. Set STT_PROVIDER=mock to
# force the dummy provider (tests do this). See docs/STT_ACTIVATION.md.
STT_PROVIDER = env("STT_PROVIDER", default="faster_whisper")
WHISPER_MODEL_SIZE = env("WHISPER_MODEL_SIZE", default="base")
WHISPER_DEVICE = env("WHISPER_DEVICE", default="cpu")       # "cpu" | "cuda" (GPU later, config-only)
WHISPER_COMPUTE_TYPE = env("WHISPER_COMPUTE_TYPE", default="int8")
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
WHISPER_DOWNLOAD_ROOT = env("WHISPER_DOWNLOAD_ROOT", default=str(BASE_DIR / "media" / "whisper-models"))
WHISPER_BEAM_SIZE = env.int("WHISPER_BEAM_SIZE", default=5)

# ffmpeg / ffprobe binaries (overridable if not on PATH). Used for audio
# extraction + normalization; absence is handled gracefully (ProcessingError).
FFMPEG_BINARY = env("FFMPEG_BINARY", default="ffmpeg")
FFPROBE_BINARY = env("FFPROBE_BINARY", default="ffprobe")
# Whisper works best on 16 kHz mono PCM WAV.
NORMALIZED_SAMPLE_RATE = env.int("NORMALIZED_SAMPLE_RATE", default=16000)

# ---------------------------------------------------------------------------
# Speaker diarization (Phase 15) — OFF by default; heavy deps in
# requirements-diarization.txt. When enabled, "embedding" (token-free) is the
# default engine; "pyannote" is opt-in and needs a free HuggingFace token.
# ---------------------------------------------------------------------------
DIARIZATION_ENABLED = env.bool("DIARIZATION_ENABLED", default=False)
DIARIZATION_PROVIDER = env("DIARIZATION_PROVIDER", default="embedding")  # embedding|pyannote|dummy
DIARIZATION_MAX_SPEAKERS = env.int("DIARIZATION_MAX_SPEAKERS", default=10)
# Cosine-distance threshold for the token-free clustering engine. ~0.5 is a
# standard ECAPA value: separates distinct speakers while resisting over-splitting
# one person into several. Lower = more speakers, higher = fewer.
DIARIZATION_CLUSTER_THRESHOLD = env.float("DIARIZATION_CLUSTER_THRESHOLD", default=0.5)
DIARIZATION_EMBEDDING_MODEL = env("DIARIZATION_EMBEDDING_MODEL", default="speechbrain/spkrec-ecapa-voxceleb")
DIARIZATION_PYANNOTE_MODEL = env("DIARIZATION_PYANNOTE_MODEL", default="pyannote/speaker-diarization-3.1")
DIARIZATION_MODEL_DIR = env("DIARIZATION_MODEL_DIR", default=str(BASE_DIR / "media" / "diarization-models"))
HUGGINGFACE_TOKEN = env("HUGGINGFACE_TOKEN", default="")
# Test-only: how many speakers the dummy provider fabricates.
DIARIZATION_DUMMY_SPEAKERS = env.int("DIARIZATION_DUMMY_SPEAKERS", default=2)

# Speaker voice signatures (Phase 15 → 15B). At processing time each diarized
# speaker gets multiple embeddings (segment/centroid/best-N) + quality signals so
# future VoicePerson recognition never re-embeds audio.
SPEAKER_STORE_SEGMENT_EMBEDDINGS = env.bool("SPEAKER_STORE_SEGMENT_EMBEDDINGS", default=True)
SPEAKER_BEST_N = env.int("SPEAKER_BEST_N", default=3)  # representative embeddings kept per speaker
SPEAKER_MIN_EMBED_DURATION = env.float("SPEAKER_MIN_EMBED_DURATION", default=0.35)  # secs to embed reliably

# Cross-meeting voice identity (Phase 15B). TIERED match thresholds (percentages)
# minimise false positives; NOTHING auto-links — the user always confirms. These
# are conservative defaults and are tunable; real-world calibration is future work.
VOICE_MATCH_AUTO_HIGHLIGHT = env.float("VOICE_MATCH_AUTO_HIGHLIGHT", default=98.0)
VOICE_MATCH_HIGHLY_LIKELY = env.float("VOICE_MATCH_HIGHLY_LIKELY", default=95.0)
VOICE_MATCH_POSSIBLE = env.float("VOICE_MATCH_POSSIBLE", default=90.0)  # suggestion floor
VOICE_MATCH_TOP_N = env.int("VOICE_MATCH_TOP_N", default=5)
VOICE_PERSON_BEST_N = env.int("VOICE_PERSON_BEST_N", default=5)  # best embeddings kept per identity

# Upload constraints. Files outside [MIN, MAX] are rejected before storage.
MAX_UPLOAD_SIZE_MB = env.int("MAX_UPLOAD_SIZE_MB", default=500)
MIN_UPLOAD_SIZE_BYTES = env.int("MIN_UPLOAD_SIZE_BYTES", default=1024)  # reject empty/near-empty
# Longest recording we accept, in seconds (best-effort — only enforced when
# the duration can be determined without ffmpeg). Default 6 hours.
MAX_AUDIO_DURATION_SECONDS = env.int("MAX_AUDIO_DURATION_SECONDS", default=6 * 3600)

# MKV is opt-in (matroska containers can wrap many codecs).
ALLOW_MKV_UPLOADS = env.bool("ALLOW_MKV_UPLOADS", default=True)

ALLOWED_UPLOAD_EXTENSIONS = ["mp3", "wav", "m4a", "aac", "flac", "ogg", "mp4", "mov", "avi", "webm"]
if ALLOW_MKV_UPLOADS:
    ALLOWED_UPLOAD_EXTENSIONS.append("mkv")

ALLOWED_UPLOAD_MIME_TYPES = [
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/aacp",
    "audio/flac",
    "audio/x-flac",
    "audio/ogg",
    "application/ogg",
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
]

# ---------------------------------------------------------------------------
# Universal media import (Phase 14) — fetch public media, then reuse the pipeline.
# ---------------------------------------------------------------------------
# Master switch. When off, the import endpoints refuse and the UI hides the tab.
MEDIA_IMPORT_ENABLED = env.bool("MEDIA_IMPORT_ENABLED", default=True)
# Optional host allow-list (empty = any PUBLIC host; private IPs are always blocked
# by the SSRF guard regardless of this list). e.g. "youtube.com,vimeo.com".
MEDIA_IMPORT_ALLOWED_HOSTS = env.list("MEDIA_IMPORT_ALLOWED_HOSTS", default=[])
# Longest media we import (reuses the upload duration cap by default).
MEDIA_IMPORT_MAX_DURATION_SECONDS = env.int(
    "MEDIA_IMPORT_MAX_DURATION_SECONDS", default=MAX_AUDIO_DURATION_SECONDS
)
# Network timeout (seconds) for feed/direct fetches.
MEDIA_IMPORT_TIMEOUT = env.int("MEDIA_IMPORT_TIMEOUT", default=60)
# Recorded on each imported Meeting for provenance.
MEDIA_IMPORTER_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "app_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "application.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
        "security_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "security.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
        "ai_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "ai.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
        "processing_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "processing.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "meetingmind": {"handlers": ["console", "app_file"], "level": "INFO", "propagate": False},
        "meetingmind.security": {"handlers": ["console", "security_file"], "level": "INFO", "propagate": False},
        "meetingmind.ai": {"handlers": ["console", "ai_file"], "level": "INFO", "propagate": False},
        "meetingmind.processing": {"handlers": ["console", "processing_file"], "level": "INFO", "propagate": False},
    },
}
