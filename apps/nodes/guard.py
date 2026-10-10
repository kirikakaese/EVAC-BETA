# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single writer for live state (ADR-0002): while an event is checked out to a venue node, live state changes on
central are forwarded to the node instead of being made here; a node does not change events it gave back.

Services call :func:`remote` and, when it is true, :func:`forward` (the change then happens on the node and comes
back through the op-log). :func:`ensure_local` guards direct writes that cannot be forwarded.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils.translation import gettext as _


class CheckedOut(Exception):
    """The event's live state is decided elsewhere (central: by its node; node: by central after check-in)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _mode() -> str:
    return getattr(settings, "EVAC_MODE", "central")


def remote(event: Any) -> bool:
    """On central: the event is checked out to a node."""
    if _mode() != "central" or event is None:
        return False
    from .models import Checkout

    return Checkout.objects.filter(event_id=event.pk, state__in=Checkout.OPEN).exists()


def read_only_copy(event: Any) -> bool:
    """On a node: the event was checked in (or never held), its live state belongs to central."""
    if _mode() != "node" or event is None:
        return False
    from .models import NodeEvent

    held = NodeEvent.objects.filter(pk=event.pk).first()
    return held is not None and not held.checked_out


def ensure_local(event: Any) -> None:
    if remote(event):
        raise CheckedOut(_("This event is checked out to a venue node; its live state is changed there."))
    if read_only_copy(event):
        raise CheckedOut(_("This event was checked in; change it on the central server."))


def forward(event: Any, kind: str, payload: dict[str, Any], *, actor: Any = None) -> Any:
    """Send a live action to the node holding ``event`` (checked here, run there)."""
    from . import central

    return central.proxy(event, kind, payload, actor=actor)


def remote_event_ids() -> set[Any]:
    if _mode() != "central":
        return set()
    from .models import Checkout

    return set(Checkout.objects.filter(state__in=Checkout.OPEN).values_list("event_id", flat=True))
