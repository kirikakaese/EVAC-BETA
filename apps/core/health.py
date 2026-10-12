# SPDX-License-Identifier: AGPL-3.0-or-later
"""The outbox health check for the heartbeat module (ADR-0052): how many deliveries wait, how old the oldest is and
how many gave up. A job that was never tried for long means the worker does not drain the outbox."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from .models import OutboxJob
from .plugins import HealthItem

#: the outbox is drained every 5 s; a job never tried after this long is stuck
WARN_AFTER = dt.timedelta(minutes=2)
DOWN_AFTER = dt.timedelta(minutes=15)


def outbox(event: Any) -> list[HealthItem]:
    now = timezone.now()
    qs = OutboxJob.objects.filter(event=event) if event is not None else OutboxJob.objects.all()
    waiting = qs.filter(status__in=[OutboxJob.Status.PENDING, OutboxJob.Status.FAILED])
    depth = waiting.count()
    oldest = qs.filter(status=OutboxJob.Status.PENDING, attempts=0).order_by("created_at").values_list(
        "created_at", flat=True).first()
    retrying = qs.filter(status=OutboxJob.Status.FAILED).count()
    dead = qs.filter(status=OutboxJob.Status.DEAD, created_at__gte=now - dt.timedelta(hours=24)).count()
    parts = [_("%(n)s waiting.") % {"n": depth}]
    if oldest is not None:
        parts.append(_("Oldest untried: %(m)s min.") % {"m": int((now - oldest).total_seconds() // 60)})
    if retrying:
        parts.append(_("%(n)s failed, retrying.") % {"n": retrying})
    if dead:
        parts.append(_("%(n)s gave up in the last 24 h.") % {"n": dead})
    status: Any = "ok"
    if oldest is not None and now - oldest > DOWN_AFTER:
        status = "down"
    elif (oldest is not None and now - oldest > WARN_AFTER) or retrying or dead:
        status = "warn"
    return [HealthItem(key="outbox", label=str(_("Outbox")), status=status, detail=" ".join(str(p) for p in parts),
                       since=oldest)]
