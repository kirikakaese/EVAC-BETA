# SPDX-License-Identifier: AGPL-3.0-or-later
"""Durable outbox: enqueue deliveries inside the business transaction, deliver them from the worker.

    from apps.core import outbox
    outbox.enqueue("webhook.deliver", {"endpoint": str(ep.pk), ...}, event=ev, key=f"wh:{ep.pk}:{delivery_id}")

Handlers are registered by plugins (``registry.outbox_handler(kind, fn)``); ``fn(job)`` raises to signal
failure (the job is retried with exponential backoff up to ``EVAC_OUTBOX_MAX_ATTEMPTS``) and may put a
JSON-able dict into ``job.result``. The idempotency key makes enqueueing the same delivery twice a no-op.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import OutboxJob
from .registry import registry

log = logging.getLogger("evac.outbox")


def enqueue(kind: str, payload: dict, *, event=None, key: str = "", deliver_now: bool = True) -> OutboxJob:
    key = key or f"{kind}:{uuid.uuid4()}"
    existing = OutboxJob.objects.filter(idempotency_key=key).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            job = OutboxJob.objects.create(kind=kind, payload=payload, event=event, idempotency_key=key)
    except IntegrityError:
        return OutboxJob.objects.get(idempotency_key=key)
    if deliver_now:
        from .tasks import deliver_job

        transaction.on_commit(lambda: deliver_job.delay(str(job.pk)))
    return job


def backoff(attempts: int) -> dt.timedelta:
    return dt.timedelta(seconds=min(2 ** attempts * 5, 3600))


def deliver(job: OutboxJob) -> bool:
    """Run the handler for one job (caller holds the row lock). Returns True when delivered."""
    if job.status in (OutboxJob.Status.DONE, OutboxJob.Status.DEAD):
        return job.status == OutboxJob.Status.DONE
    handler = registry.ensure_loaded().outbox_handlers.get(job.kind)
    job.attempts += 1
    if handler is None:
        job.status = OutboxJob.Status.DEAD
        job.last_error = f"no handler registered for {job.kind!r}"
        job.save(update_fields=["attempts", "status", "last_error"])
        return False
    try:
        handler(job)
    except Exception as exc:  # noqa: BLE001 - any handler failure is a retryable delivery failure
        log.warning("outbox job %s (%s) failed: %s", job.pk, job.kind, exc)
        job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        max_attempts = getattr(settings, "EVAC_OUTBOX_MAX_ATTEMPTS", 8)
        if job.attempts >= max_attempts:
            job.status = OutboxJob.Status.DEAD
        else:
            job.status = OutboxJob.Status.FAILED
            job.next_attempt_at = timezone.now() + backoff(job.attempts)
        job.save(update_fields=["attempts", "status", "last_error", "next_attempt_at", "result"])
        return False
    job.status = OutboxJob.Status.DONE
    job.delivered_at = timezone.now()
    job.last_error = ""
    job.save(update_fields=["attempts", "status", "last_error", "delivered_at", "result"])
    return True


def due_jobs(limit: int = 100):
    return (OutboxJob.objects.filter(status__in=[OutboxJob.Status.PENDING, OutboxJob.Status.FAILED],
                                     next_attempt_at__lte=timezone.now()).order_by("next_attempt_at")[:limit])


def depth() -> int:
    return OutboxJob.objects.filter(status__in=[OutboxJob.Status.PENDING, OutboxJob.Status.FAILED]).count()
