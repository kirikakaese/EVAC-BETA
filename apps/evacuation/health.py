# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hardware bridges for the heartbeat module's health monitor (ADR-0052, ADR-0032). Read-only: it reports what the
bridge supervision already records (last heartbeat, input faults) and never changes a bridge, an input or an alarm
state. The bridge supervision keeps its own alerts (``bridges.sweep``)."""
from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.plugins import HealthItem, HealthStatus

from .bridges import OFFLINE_AFTER
from .models import Bridge


def check(event: Any) -> list[HealthItem]:
    now = timezone.now()
    url = reverse("evacuation:bridges", args=[event.slug])
    out = []
    for bridge in Bridge.objects.filter(event=event):
        status: HealthStatus
        if bridge.last_seen is None:
            status, detail = "unknown", str(_("Never connected."))
        elif (now - bridge.last_seen).total_seconds() > OFFLINE_AFTER:
            status = "down"
            detail = str(_("No heartbeat since %(t)s: its inputs cannot raise alarms.")
                         % {"t": timezone.localtime(bridge.last_seen, event.tz).strftime("%H:%M:%S")})
        else:
            inputs = (bridge.status or {}).get("inputs") or {}
            faults = sorted(str(k) for k, v in inputs.items() if v == "fault")
            if faults:
                status = "warn"
                detail = str(_("Input fault (broken loop?): %(i)s") % {"i": ", ".join(faults)})
            else:
                status, detail = "ok", str(_("Heartbeat received (%(t)s).") % {"t": bridge.transport or "https"})
        out.append(HealthItem(key=str(bridge.pk), label=str(bridge.name), status=status, detail=detail,
                              since=bridge.last_seen, url=url))
    return out
