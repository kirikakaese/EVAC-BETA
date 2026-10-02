# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery application (worker + beat)."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evac.settings.dev")

app = Celery("evac")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
