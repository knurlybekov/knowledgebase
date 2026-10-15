"""Test overrides. Selected by pyproject [tool.pytest.ini_options].

Every secret that base.py reads MUST be forced to "" or a deterministic value
here in the same commit that adds it, or a developer .env leaks real keys into
the suite and tests make billed calls.
"""

import tempfile

from cryptography.fernet import Fernet

from .base import *  # noqa: F403
from .base import DATABASES, LOGGING, STORAGES

STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
WHITENOISE_AUTOREFRESH = True

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMBEDDER = "mock"
EMBEDDING_DIM = 1536
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_MODEL_VERSION = "2024-01"
OPENAI_API_KEY = ""
ANTHROPIC_API_KEY = ""
LLM_PROVIDER = "stub"
LLM_MODEL = ""
MICROSOFT_CLIENT_ID = "test-ms-client"
MICROSOFT_CLIENT_SECRET = ""
GOOGLE_CLIENT_ID = "test-google-client"
GOOGLE_CLIENT_SECRET = ""
CONNECTOR_TOKEN_KEY = Fernet.generate_key().decode()
HERMES_ENABLED = True
RUNNER_URL = "http://runner.test"
RUNNER_SHARED_SECRET = "test-runner-secret"
METRICS_TOKEN = "test-metrics-token"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
RATE_LIMIT_SEARCH_PER_MIN = 100_000
RATE_LIMIT_INVESTIGATION_PER_HOUR = 100_000
RATE_LIMIT_LOGIN_PER_15MIN = 100_000
ALLOWED_HOSTS = ["*"]
DATABASES["default"]["ATOMIC_REQUESTS"] = True
MEDIA_ROOT = tempfile.mkdtemp(prefix="kb-test-media-")

LOGGING["root"]["level"] = "WARNING"
for _logger in LOGGING["loggers"].values():
    _logger["level"] = "WARNING"
