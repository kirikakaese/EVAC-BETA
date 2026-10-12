# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health checks of venue nodes for the heartbeat module (ADR-0052, ADR-0036): read-only, database only.

* event (central): the node holding the event, by its last contact and sync;
* instance (central): every enrolled node; a node without a checked-out event may be switched off, so it never
  counts as down;
* instance (node): the link to central. A venue works offline, so a lost link is "degraded", never "down".
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.plugins import HealthItem, HealthStatus

from .models import Checkout, Node, NodeIdentity

#: a node talks to central every few seconds while it holds an event
OK_SECONDS = 60
DOWN_SECONDS = 300


def _age(at: dt.datetime | None, now: dt.datetime) -> float | None:
    return (now - at).total_seconds() if at is not None else None


def _status(age: float | None) -> HealthStatus:
    if age is None:
        return "unknown"
    if age <= OK_SECONDS:
        return "ok"
    return "warn" if age <= DOWN_SECONDS else "down"


def _ago(age: float | None) -> str:
    if age is None:
        return str(_("never"))
    if age < 120:
        return str(_("%(s)s s ago") % {"s": int(age)})
    return str(_("%(m)s min ago") % {"m": int(age // 60)})


def event_check(event: Any) -> list[HealthItem]:
    """The venue node holding ``event`` (central only)."""
    if getattr(settings, "EVAC_MODE", "central") != "central" or event is None:
        return []
    co = Checkout.objects.filter(event=event, state__in=Checkout.OPEN).select_related("node").first()
    if co is None:
        return []
    now = timezone.now()
    age = _age(co.node.last_seen, now)
    detail = _("Last contact %(c)s, last sync %(s)s.") % {"c": _ago(age), "s": _ago(_age(co.last_sync, now))}
    return [HealthItem(key=str(co.node_id), label=str(_("Venue node %(n)s") % {"n": co.node.name}),
                       status=_status(age), detail=str(detail), since=co.node.last_seen,
                       url=reverse("nodes:index", args=[event.slug]))]


def instance_check(event: Any) -> list[HealthItem]:
    now = timezone.now()
    if getattr(settings, "EVAC_MODE", "central") == "node":
        ident = NodeIdentity.objects.filter(pk=1).first()
        if ident is None or ident.enrolled_at is None:
            return []
        age = _age(ident.last_contact, now)
        status: HealthStatus = "ok" if age is not None and age <= OK_SECONDS else "warn"
        detail = _("Last contact with central %(c)s.") % {"c": _ago(age)}
        if ident.last_error:
            detail = f"{detail} {ident.last_error}"
        return [HealthItem(key="central", label=str(_("Link to central")), status=status, detail=str(detail)[:500],
                           since=ident.last_contact)]
    holding = set(Checkout.objects.filter(state__in=Checkout.OPEN).values_list("node_id", flat=True))
    out = []
    for node in Node.objects.filter(enrolled_at__isnull=False, revoked_at__isnull=True):
        age = _age(node.last_seen, now)
        st = _status(age)
        if node.pk not in holding and st != "ok":
            st = "unknown"  # idle nodes may be switched off
        detail = _("Last contact %(c)s.") % {"c": _ago(age)}
        if node.pk not in holding:
            detail = f"{detail} {_('No event checked out.')}"
        out.append(HealthItem(key=str(node.pk), label=str(_("Venue node %(n)s") % {"n": node.name}), status=st,
                              detail=str(detail), since=node.last_seen, url=reverse("nodes_admin:index")))
    return out
