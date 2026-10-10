# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operations on venue nodes (ADR-0036): escalation rules are configuration from central; incidents, their
timeline, the ops log and tasks are live on the node during a checkout (ADR-0002 lists incidents as node data)."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import Escalation, EscalationRule, Incident, IncidentUpdate, LogEntry, Task

    return SyncSpec(module="ops", order=150, models=(
        SyncModel("ops.EscalationRule", lambda e: EscalationRule.objects.filter(event=e)),
        SyncModel("ops.Incident", lambda e: Incident.objects.filter(event=e), live=True),
        SyncModel("ops.IncidentUpdate", lambda e: IncidentUpdate.objects.filter(incident__event=e), live=True,
                  files=lambda u: [(u.attachment.name, "")] if u.attachment else []),
        SyncModel("ops.Escalation", lambda e: Escalation.objects.filter(incident__event=e), live=True),
        SyncModel("ops.LogEntry", lambda e: LogEntry.objects.filter(event=e), live=True),
        SyncModel("ops.Task", lambda e: Task.objects.filter(event=e), live=True),
    ))
