"""Settings package. `knowledgebase.settings` resolves to the base settings.

Select a variant with DJANGO_SETTINGS_MODULE:
  knowledgebase.settings       -> base (dev and production, driven by .env)
  knowledgebase.settings.test  -> test overrides (stub providers, eager Celery)
"""

from .base import *  # noqa: F403
