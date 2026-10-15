"""Base settings, read from the environment (django-environ).

Secrets have no defaults: a missing SECRET_KEY, DATABASE_URL or
CONNECTOR_TOKEN_KEY stops the process at import time. Durations are seconds.
"""

from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:8000"]),
    LOG_LEVEL=(str, "INFO"),
    # --- Celery ---
    CELERY_BROKER_URL=(str, "redis://localhost:6381/0"),
    CELERY_RESULT_BACKEND=(str, "redis://localhost:6381/1"),
    CELERY_TASK_ALWAYS_EAGER=(bool, False),
    # --- Embeddings (retrieval.embedding factory) ---
    EMBEDDER=(str, "mock"),
    EMBEDDING_MODEL=(str, "text-embedding-3-small"),
    EMBEDDING_MODEL_VERSION=(str, "2024-01"),
    EMBEDDING_DIM=(int, 1536),
    OPENAI_API_KEY=(str, ""),
    # --- Answer LLM (answers.composer factory): anthropic | openai | stub ---
    LLM_PROVIDER=(str, "stub"),
    LLM_MODEL=(str, ""),
    ANTHROPIC_API_KEY=(str, ""),
    # --- Connectors ---
    MICROSOFT_CLIENT_ID=(str, ""),
    MICROSOFT_CLIENT_SECRET=(str, ""),
    MICROSOFT_TENANT=(str, "organizations"),
    GOOGLE_CLIENT_ID=(str, ""),
    GOOGLE_CLIENT_SECRET=(str, ""),
    SYNC_INTERVAL_S=(int, 900),
    LEASE_TTL_S=(int, 300),
    PERMISSION_FRESHNESS_MAX_AGE_S=(int, 24 * 3600),
    FULL_RECONCILE_INTERVAL_S=(int, 12 * 3600),
    PURGE_GRACE_S=(int, 48 * 3600),
    DERIVED_PURGE_GRACE_S=(int, 7 * 24 * 3600),
    DOWNLOAD_MAX_BYTES=(int, 50 * 1024 * 1024),
    # --- Hermes investigations ---
    HERMES_ENABLED=(bool, False),
    RUNNER_URL=(str, "http://hermes-agent:8700"),
    RUNNER_SHARED_SECRET=(str, ""),
    INVESTIGATION_MAX_TURNS=(int, 12),
    INVESTIGATION_MAX_TOOL_CALLS=(int, 20),
    INVESTIGATION_TIMEOUT_S=(int, 180),
    INVESTIGATION_MAX_OUTPUT_CHARS=(int, 60_000),
    INVESTIGATION_MAX_RETRIES=(int, 1),
    DISPATCH_TIMEOUT_S=(int, 60),
    HEARTBEAT_INTERVAL_S=(int, 10),
    MCP_MIN_RESPONSE_CHARS=(int, 200),
    # --- Request limits ---
    RATE_LIMIT_SEARCH_PER_MIN=(int, 60),
    RATE_LIMIT_INVESTIGATION_PER_HOUR=(int, 20),
    RATE_LIMIT_LOGIN_PER_15MIN=(int, 10),
    METRICS_TOKEN=(str, ""),
)
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django_htmx",
    "django_tailwind_cli",
    # Local apps. Cross-app imports go through <app>/api.py (eval/test_module_boundaries.py).
    "infra",
    "accounts",
    "organizations",
    "connectors",
    "knowledge",
    "retrieval",
    "answers",
    "investigations",
    "mcp_server",
    "decisions",
    "web",
    "eval",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "infra.middleware.RequestContextMiddleware",
    "organizations.middleware.OrganizationContextMiddleware",
]

ROOT_URLCONF = "knowledgebase.urls"
WSGI_APPLICATION = "knowledgebase.wsgi.application"
ASGI_APPLICATION = "knowledgebase.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "organizations.context_processors.organization",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database: Postgres only. The URL names the role; production and dev use
# kb_app at runtime and kb_migrator for migrations (see scripts/postgres-init).
# ---------------------------------------------------------------------------
DATABASES = {"default": env.db_url("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 0
# Each request runs in one transaction so SET LOCAL app.org_id covers all of it.
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "web:home"
LOGOUT_REDIRECT_URL = "accounts:login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "web" / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
TAILWIND_CLI_SRC_CSS = BASE_DIR / "web" / "tailwind" / "source.css"
TAILWIND_CLI_DIST_CSS = "css/dist/styles.css"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CELERY_RESULT_BACKEND"),
    }
}

# ---------------------------------------------------------------------------
# Celery. Short transactions per write (D5); long tasks are lease-fenced.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND")
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER")
CELERY_TASK_EAGER_PROPAGATES = CELERY_TASK_ALWAYS_EAGER
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_TIMEZONE = TIME_ZONE
CELERY_RESULT_EXPIRES = 24 * 3600
CELERY_BEAT_SCHEDULE = {
    "connectors-schedule-syncs": {
        "task": "connectors.tasks.schedule_syncs",
        "schedule": timedelta(seconds=60),
    },
    "knowledge-expiration-sweep": {
        "task": "knowledge.tasks.expiration_sweep",
        "schedule": timedelta(minutes=30),
    },
    "investigations-reaper": {
        "task": "investigations.tasks.reap_investigations",
        "schedule": timedelta(seconds=30),
    },
}

# ---------------------------------------------------------------------------
# Embeddings and LLM
# ---------------------------------------------------------------------------
EMBEDDER = env("EMBEDDER")
EMBEDDING_MODEL = env("EMBEDDING_MODEL")
EMBEDDING_MODEL_VERSION = env("EMBEDDING_MODEL_VERSION")
EMBEDDING_DIM = env("EMBEDDING_DIM")
OPENAI_API_KEY = env("OPENAI_API_KEY")
LLM_PROVIDER = env("LLM_PROVIDER")
LLM_MODEL = env("LLM_MODEL")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")

# ---------------------------------------------------------------------------
# Connectors and permission freshness (D3)
# ---------------------------------------------------------------------------
CONNECTOR_TOKEN_KEY = env("CONNECTOR_TOKEN_KEY")
MICROSOFT_CLIENT_ID = env("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = env("MICROSOFT_CLIENT_SECRET")
MICROSOFT_TENANT = env("MICROSOFT_TENANT")
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")
SYNC_INTERVAL_S = env("SYNC_INTERVAL_S")
LEASE_TTL_S = env("LEASE_TTL_S")
PERMISSION_FRESHNESS_MAX_AGE_S = env("PERMISSION_FRESHNESS_MAX_AGE_S")
FULL_RECONCILE_INTERVAL_S = env("FULL_RECONCILE_INTERVAL_S")
PURGE_GRACE_S = env("PURGE_GRACE_S")
DERIVED_PURGE_GRACE_S = env("DERIVED_PURGE_GRACE_S")
DOWNLOAD_MAX_BYTES = env("DOWNLOAD_MAX_BYTES")
if FULL_RECONCILE_INTERVAL_S > PERMISSION_FRESHNESS_MAX_AGE_S // 2:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "FULL_RECONCILE_INTERVAL_S must be at most half of PERMISSION_FRESHNESS_MAX_AGE_S, "
        "or grants expire between two complete revalidations."
    )

# ---------------------------------------------------------------------------
# Hermes investigations (D1) and MCP budgets
# ---------------------------------------------------------------------------
HERMES_ENABLED = env("HERMES_ENABLED")
RUNNER_URL = env("RUNNER_URL")
RUNNER_SHARED_SECRET = env("RUNNER_SHARED_SECRET")
INVESTIGATION_LIMITS = {
    "max_turns": env("INVESTIGATION_MAX_TURNS"),
    "max_tool_calls": env("INVESTIGATION_MAX_TOOL_CALLS"),
    "timeout_s": env("INVESTIGATION_TIMEOUT_S"),
    "max_output_chars": env("INVESTIGATION_MAX_OUTPUT_CHARS"),
    "max_retries": env("INVESTIGATION_MAX_RETRIES"),
}
DISPATCH_TIMEOUT_S = env("DISPATCH_TIMEOUT_S")
HEARTBEAT_INTERVAL_S = env("HEARTBEAT_INTERVAL_S")
MCP_MIN_RESPONSE_CHARS = env("MCP_MIN_RESPONSE_CHARS")

# ---------------------------------------------------------------------------
# Request limits and metrics
# ---------------------------------------------------------------------------
RATE_LIMIT_SEARCH_PER_MIN = env("RATE_LIMIT_SEARCH_PER_MIN")
RATE_LIMIT_INVESTIGATION_PER_HOUR = env("RATE_LIMIT_INVESTIGATION_PER_HOUR")
RATE_LIMIT_LOGIN_PER_15MIN = env("RATE_LIMIT_LOGIN_PER_15MIN")
METRICS_TOKEN = env("METRICS_TOKEN")

# ---------------------------------------------------------------------------
# Logging: one JSON object per line with org_id, actor_id, request_id.
# ---------------------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "infra.logging.JsonFormatter"}},
    "filters": {"request_context": {"()": "infra.logging.RequestContextFilter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_context"],
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "celery": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
