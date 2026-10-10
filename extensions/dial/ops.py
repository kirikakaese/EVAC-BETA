# SPDX-License-Identifier: AGPL-3.0-or-later
"""DECT alerts from DIAL into EVAC's operations view.

Until the operations log arrives (roadmap 6.1) an alert is kept as a ``DectAlert`` (DECT status data source and the
DIAL page), written to the extension log, sent to integrations as ``dial.dect_alert`` and, when it is a problem
(an RFP down, sync degraded, the OMM unreachable), notified to the people who may see the DIAL status.
"""
from __future__ import annotations

from typing import Any

from django.urls import reverse
from django.utils.translation import gettext as _

PERM_STATUS = "dial.status"


def watchers(event: Any) -> list[Any]:
    from apps.events import rbac
    from apps.events.models import Membership

    users = [m.user for m in Membership.objects.filter(event=event).select_related("user") if m.user.is_active]
    return [u for u in users if rbac.has_any(u, event, PERM_STATUS)]


def dect_alert(config: Any, alert: Any, *, problem: bool) -> None:
    from apps.core import webhooks
    from apps.core.notify import notify

    event = config.event
    webhooks.emit("dial.dect_alert", {"event": event.slug, "kind": alert.kind, "severity": alert.severity,
                                      "message": alert.message, "rfp": alert.rfp, "at": alert.at.isoformat()},
                  event=event)
    if problem:
        title = _("DECT: %(kind)s") % {"kind": alert.kind}
        notify(watchers(event), title, body=alert.message or alert.rfp, level="warn", event=event,
               url=reverse("dial:status", args=[event.slug]))
