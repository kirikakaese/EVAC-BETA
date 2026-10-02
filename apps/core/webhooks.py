# SPDX-License-Identifier: AGPL-3.0-or-later
"""Emit internal events to outbound integrations.

    from apps.core.webhooks import emit
    emit("event.state_changed", {"slug": ev.slug, "from": "setup", "to": "live"}, event=ev)

``emit`` publishes to the realtime stream of the event and hands the event to every registered webhook
sink (the generic webhook extension enqueues signed deliveries in the outbox). Event types must be
registered with ``registry.webhook_event`` so integrators can discover them.
"""
from __future__ import annotations

import logging
from typing import Any

from .registry import registry

log = logging.getLogger("evac.webhooks")


def emit(event_type: str, payload: dict[str, Any], *, event=None) -> None:
    reg = registry.ensure_loaded()
    if event_type not in reg.webhook_events:
        raise KeyError(f"unregistered webhook event type {event_type!r}")
    reg.call_sinks(event_type, payload, event)
    if event is not None:
        from .realtime import publish

        publish(event, event_type, payload)
