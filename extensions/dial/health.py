# SPDX-License-Identifier: AGPL-3.0-or-later
"""The DIAL link for the heartbeat module's health monitor (ADR-0052): from what EVAC already knows (the last
connection test, the last status fetch, recent broadcasts). Read-only, no call to DIAL here: the outbox fetches."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.plugins import HealthItem

from . import link


def check(event: Any) -> list[HealthItem]:
    from apps.extensions import services as ext
    from apps.extensions.models import ExtensionConfig

    from .models import Broadcast, Snapshot

    config = ext.effective(link.KEY, event)
    if config is None:
        return []
    url = reverse("dial:status", args=[event.slug])
    label = str(_("DIAL link"))
    if config.health == ExtensionConfig.Health.ERROR:
        return [HealthItem(key="dial", label=label, status="down", url=url, since=config.last_check_at,
                           detail=str(_("The last connection test failed: %(e)s") % {
                               "e": (config.last_error or "?")[:300]}))]
    problems = []
    snap = Snapshot.objects.filter(config=config, key="dect").first()
    if snap is not None and snap.error:
        problems.append(str(_("Status fetch failed: %(e)s") % {"e": snap.error[:200]}))
    failed = Broadcast.objects.filter(config=config, event=event, status=Broadcast.Status.FAILED,
                                      created_at__gte=timezone.now() - dt.timedelta(hours=1)).count()
    if failed:
        problems.append(str(_("%(n)s broadcasts failed in the last hour.") % {"n": failed}))
    if problems:
        return [HealthItem(key="dial", label=label, status="warn", detail=" ".join(problems), url=url,
                           since=snap.fetched_at if snap is not None else config.last_check_at)]
    if config.health == ExtensionConfig.Health.UNKNOWN:
        return [HealthItem(key="dial", label=label, status="unknown", url=url,
                           detail=str(_("Not tested yet: use “Test connection” in Settings → Extensions → DIAL.")))]
    detail = str(_("Connection test passed."))
    if snap is not None and snap.fetched_at:
        at = timezone.localtime(snap.fetched_at, event.tz).strftime("%H:%M")
        detail = f"{detail} {_('DECT status fetched at %(t)s.') % {'t': at}}"
    return [HealthItem(key="dial", label=label, status="ok", detail=detail, url=url, since=config.last_check_at)]
