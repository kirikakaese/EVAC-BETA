# SPDX-License-Identifier: AGPL-3.0-or-later
"""The screens panel of the control room dashboard (ADR-0039): how many screens are online, which are not."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.events import rbac

from . import services
from .models import Screen


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    if not rbac.has_any(request.user, event, "screens.view", request=request):
        return None
    cfg = services.screen_settings(event)
    now = timezone.now()
    counts = {k: 0 for k in Screen.Health.values}
    problems = []
    for s in Screen.objects.filter(event=event, revoked_at__isnull=True).exclude(token_hash="").select_related(
            "room"):
        h = s.health(heartbeat_seconds=cfg["heartbeat_seconds"], offline_after=cfg["offline_after_seconds"], now=now)
        counts[h] = counts.get(h, 0) + 1
        if h in (Screen.Health.OFFLINE, Screen.Health.STALE):
            problems.append({"screen": s, "health": h, "label": Screen.Health(h).label})
    return {"online": counts[Screen.Health.ONLINE], "stale": counts[Screen.Health.STALE],
            "offline": counts[Screen.Health.OFFLINE], "problems": problems[:10],
            "total": sum(counts.values())}
