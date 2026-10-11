# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation alarms to staff through notification channels (ADR-0049): a second path besides Web Push and the
staff app, for the channels chosen in the evacuation settings (``staff_alarm_channels``). Every state change goes
out through the outbox after the screens have theirs; drills are marked; alerts are ``critical`` so a channel that
cannot keep strangers from posting (an ntfy topic without an access token) refuses them."""
from __future__ import annotations

from typing import Any

from apps.core import alerts, settings_store
from apps.core.plugins import Alert

LEVEL = {"evacuate": "err", "shelter_in_place": "err", "attention": "warn", "staff_alert": "warn",
         "all_clear": "info"}


def message(event: Any, entry: Any) -> Alert | None:
    """The alert for a state change, or None (back to normal after an all clear is not news)."""
    from .services import config

    if entry.to_state not in LEVEL:
        return None
    cfg = config(event)
    label = cfg.labels.get(entry.to_state, entry.to_state)
    where = entry.zone_name or event.name
    prefix = f"{cfg.drill_text}: " if entry.drill else ""
    level = "warn" if entry.drill and LEVEL[entry.to_state] == "err" else LEVEL[entry.to_state]
    lines = [f"{label}: {where}" + (f" ({cfg.drill_text})" if entry.drill else "")]
    if entry.reason:
        lines.append(entry.reason)
    lines.append("Open the EVAC staff app for instructions." if entry.to_state != "all_clear"
                 else "Return to normal duties when the control room says so.")
    return Alert(title=f"{prefix}{label} – {where}"[:200], body="\n".join(lines), level=level,
                 url=f"/e/{event.slug}/staff/", key=f"evac:{entry.pk}", critical=True)


def send(event: Any, entry: Any) -> int:
    """Queue the alert for the configured channels; returns how many channels got it."""
    keys = [str(k) for k in settings_store.get("evacuation", event=event).get("staff_alarm_channels") or []]
    alert = message(event, entry) if keys else None
    if alert is None:
        return 0
    return alerts.enqueue(event, keys, alert)
