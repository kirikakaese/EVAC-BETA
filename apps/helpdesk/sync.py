# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpdesk on venue nodes (ADR-0036): requests and lost & found are live during a checkout, the FAQ is config."""
from __future__ import annotations

from apps.core.plugins import SyncModel, SyncSpec


def spec() -> SyncSpec:
    from .models import FaqEntry, LostFound, Ticket, TicketNote

    def photo(obj):  # type: ignore[no-untyped-def]
        return [(obj.photo.name, "")] if obj.photo else []

    return SyncSpec(module="helpdesk", order=190, models=(
        SyncModel("helpdesk.FaqEntry", lambda e: FaqEntry.objects.filter(event=e)),
        SyncModel("helpdesk.LostFound", lambda e: LostFound.objects.filter(event=e), live=True, files=photo),
        SyncModel("helpdesk.Ticket", lambda e: Ticket.objects.filter(event=e), live=True),
        SyncModel("helpdesk.TicketNote", lambda e: TicketNote.objects.filter(ticket__event=e), live=True),
    ))
