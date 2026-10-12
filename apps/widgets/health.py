# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data feeds for the heartbeat module's health monitor (ADR-0052): feeds whose last fetch failed or whose data is
old. Never "down": screens keep showing the last good data."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import gettext as _

from apps.core.plugins import HealthItem

from .models import Feed


def check(event: Any) -> list[HealthItem]:
    now = timezone.now()
    out = []
    for feed in Feed.objects.filter(event=event, enabled=True).exclude(kind=Feed.Kind.SOURCE):
        url = reverse("widgets:index", args=[event.slug])
        stale = feed.last_success_at is not None and now - feed.last_success_at > dt.timedelta(
            seconds=max(3 * feed.poll_seconds, 600))
        if feed.status == Feed.Status.ERROR or stale:
            detail = _("Last good data: %(t)s ago.") % {"t": timesince(feed.last_success_at, now)} \
                if feed.last_success_at else _("No good data yet.")
            if feed.error:
                detail = f"{detail} {feed.error[:300]}"
            out.append(HealthItem(key=str(feed.pk), label=feed.name, status="warn", detail=str(detail),
                                  since=feed.last_success_at, url=url))
        elif feed.status == Feed.Status.OK:
            out.append(HealthItem(key=str(feed.pk), label=feed.name, status="ok", since=feed.last_success_at,
                                  detail=str(_("Fetched.")), url=url))
    return out
