# SPDX-License-Identifier: AGPL-3.0-or-later
"""The screens health check for the heartbeat module (ADR-0052): every paired screen by its last heartbeat, with the
same thresholds as the screens list (``heartbeat_seconds``, ``offline_after_seconds``)."""
from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import gettext as _

from apps.core.plugins import HealthItem

from . import services
from .models import Screen

STATUS = {Screen.Health.ONLINE: "ok", Screen.Health.STALE: "warn", Screen.Health.OFFLINE: "down"}


def check(event: Any) -> list[HealthItem]:
    cfg = services.screen_settings(event)
    now = timezone.now()
    out = []
    paired = Screen.objects.filter(event=event, revoked_at__isnull=True, token_hash__isnull=False).exclude(
        token_hash="")
    for s in paired.select_related("room"):
        h = s.health(heartbeat_seconds=cfg["heartbeat_seconds"], offline_after=cfg["offline_after_seconds"], now=now)
        if s.last_seen_at is None:
            detail = _("Paired, never connected.")
        elif h == Screen.Health.ONLINE:
            detail = _("Online.")
        else:
            detail = _("No heartbeat for %(t)s.") % {"t": timesince(s.last_seen_at, now)}
        if s.room_id:
            detail = f"{s.room.name} · {detail}"
        status = STATUS.get(h, "unknown") if s.last_seen_at is not None else "unknown"
        out.append(HealthItem(key=str(s.pk), label=s.name, status=status, detail=detail, since=s.last_seen_at,
                              url=reverse("screens:detail", args=[event.slug, s.pk])))
    return out
