# SPDX-License-Identifier: AGPL-3.0-or-later
"""Staff alerts through notification channels (ADR-0039): incident escalations, "room full" and the like go to the
channels an event has (ntfy, Matrix, Telegram, e-mail, DIAL DECT messages) through the outbox, so a slow or broken
service never holds up the request and failed sends are retried."""
from __future__ import annotations

from typing import Any

from . import modules, outbox
from .plugins import Alert
from .registry import registry

JOB = "core.alert"


def channels(event: Any) -> dict[str, str]:
    """Channels of ``event`` that can send staff alerts: ``{key: name}``."""
    out = {}
    for key, spec in registry.ensure_loaded().notification_channels.items():
        if spec.alert is None:
            continue
        if spec.module != "core" and not modules.is_enabled(spec.module, event):
            continue
        if spec.available is not None and not spec.available(event):
            continue
        out[key] = spec.name
    return out


def enqueue(event: Any, keys: list[str], alert: Alert) -> int:
    """Queue ``alert`` for each channel in ``keys`` (unknown or unavailable ones are skipped). Idempotent per
    ``alert.key`` and channel."""
    usable = channels(event)
    n = 0
    for key in keys:
        if key not in usable:
            continue
        outbox.enqueue(JOB, {"channel": key, "title": alert.title, "body": alert.body, "level": alert.level,
                             "url": alert.url, "key": alert.key}, event=event,
                       key=f"alert:{key}:{alert.key}" if alert.key else "")
        n += 1
    return n


def handle_job(job: Any) -> None:
    p = job.payload
    spec = registry.ensure_loaded().notification_channels.get(p.get("channel", ""))
    if spec is None or spec.alert is None or job.event is None:
        job.result = {"skipped": "channel gone"}
        return
    result = spec.alert(job.event, Alert(title=p.get("title", ""), body=p.get("body", ""),
                                         level=p.get("level", "info"), url=p.get("url", ""), key=p.get("key", "")))
    job.result = dict(result or {})
