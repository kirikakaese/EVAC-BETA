# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screens get new evacuation payloads when settings that shape them change (ADR-0033)."""
from __future__ import annotations

from typing import Any

NAMESPACES = ("evacuation", "evacuation_screen", "display")


def settings_changed(sender: Any, instance: Any, **kwargs: Any) -> None:
    if instance.namespace not in NAMESPACES:
        return
    from apps.core import modules
    from apps.events.models import Event

    from . import feed

    level, scope = instance.level, instance.scope_id
    if level == "event":
        events = list(Event.objects.filter(pk=scope))
    elif level == "screen":
        from apps.screens.models import Screen

        events = [s.event for s in Screen.objects.filter(pk=scope).select_related("event")]
    else:  # instance, venue or screen group: every event that may have such screens
        events = list(Event.objects.exclude(state="archived"))
    for event in events:
        if modules.is_enabled("evacuation", event):
            feed.push(event)
