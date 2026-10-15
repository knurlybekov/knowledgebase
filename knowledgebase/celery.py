"""Celery application. Tasks are discovered from <app>/tasks.py."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "knowledgebase.settings")

app = Celery("knowledgebase")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
