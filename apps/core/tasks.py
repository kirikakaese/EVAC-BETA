# SPDX-License-Identifier: AGPL-3.0-or-later
"""Celery tasks of the core: outbox delivery."""
from __future__ import annotations

import datetime as dt

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from . import outbox
from .models import OutboxJob


def _locked(job_id):
    qs = OutboxJob.objects.filter(pk=job_id)
    if transaction.get_connection().features.has_select_for_update_skip_locked:
        qs = qs.select_for_update(skip_locked=True)
    return qs.first()


@shared_task(name="apps.core.tasks.deliver_job")
def deliver_job(job_id: str) -> bool:
    with transaction.atomic():
        job = _locked(job_id)
        if job is None:
            return False
        if job.next_attempt_at > timezone.now() and job.attempts:
            return False
        return outbox.deliver(job)


@shared_task(name="apps.core.tasks.drain_outbox")
def drain_outbox(limit: int = 100) -> int:
    delivered = 0
    for job_id in list(outbox.due_jobs(limit).values_list("pk", flat=True)):
        with transaction.atomic():
            job = _locked(job_id)
            if job is not None and outbox.deliver(job):
                delivered += 1
    return delivered


@shared_task(name="apps.core.tasks.purge_delivered_outbox")
def purge_delivered_outbox(days: int = 14) -> int:
    cutoff = timezone.now() - dt.timedelta(days=days)
    deleted, _ = OutboxJob.objects.filter(status=OutboxJob.Status.DONE, delivered_at__lt=cutoff).delete()
    return deleted
