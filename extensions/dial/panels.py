# SPDX-License-Identifier: AGPL-3.0-or-later
"""The DIAL/DECT panel of the control room dashboard (ADR-0039): base stations and recent DECT alerts."""
from __future__ import annotations

from typing import Any

from apps.events import rbac

from . import link


def dashboard(request: Any, event: Any) -> dict[str, Any] | None:
    from apps.extensions import services as ext

    from .models import DectAlert

    config = ext.effective(link.KEY, event)
    if config is None or not rbac.has_any(request.user, event, "dial.status", request=request):
        return None
    snap = None
    if config.feature_enabled("data_sources"):
        from .models import Snapshot

        snap = Snapshot.objects.filter(config=config, key="dect").first()  # no fetch here: the page refreshes it
    return {"dect": (snap.data or {}) if snap is not None else None, "error": snap.error if snap else "",
            "checked": snap.fetched_at if snap else None, "alerts": list(DectAlert.objects.filter(config=config)[:5])}
