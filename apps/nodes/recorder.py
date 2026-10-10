# SPDX-License-Identifier: AGPL-3.0-or-later
"""On a venue node: record every change of live state in the op-log (ADR-0002, ADR-0036).

Signals catch saves and deletes of the live models of every ``r.sync`` spec and every new audit row, for events
this node holds checked out. Changes made while a snapshot is being applied are not recorded. Entries are
numbered per event (``NodeEvent.next_seq``) in the same transaction as the change.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models, transaction
from django.db.models import F
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.utils import timezone

_live: set[str] | None = None


def is_node() -> bool:
    return getattr(settings, "EVAC_MODE", "central") == "node"


def live() -> set[str]:
    global _live
    if _live is None:
        from . import snapshot

        _live = snapshot.live_labels()
    return _live


def event_id_of(obj: Any) -> Any:
    """The event a row belongs to: its ``event_id``, or that of the row it points to (one step)."""
    if getattr(obj, "event_id", None):
        return obj.event_id
    for f in obj._meta.concrete_fields:
        if isinstance(f, models.ForeignKey):
            target = getattr(obj, f.name, None)
            if target is not None and getattr(target, "event_id", None):
                return target.event_id
    return None


def record(event_id: Any, kind: str, *, model: str = "", object_id: str = "", data: dict[str, Any]) -> Any:
    from .models import NodeEvent, NodeIdentity, OpLogEntry

    with transaction.atomic():
        if not NodeEvent.objects.filter(pk=event_id, checked_out=True).update(next_seq=F("next_seq") + 1):
            return None  # not an event this node holds
        seq, checkout = NodeEvent.objects.values_list("next_seq", "checkout_id").get(pk=event_id)
        seq -= 1
        node = NodeIdentity.objects.values_list("node_id", flat=True).filter(pk=1).first()
        return OpLogEntry.objects.create(event_id=event_id, node_id=node, seq=seq, key=f"{checkout}:{seq}",
                                         kind=kind, model=model, object_id=object_id, data=data,
                                         created_at=timezone.now())


def _skip(raw: bool = False) -> bool:
    from . import snapshot

    return raw or not is_node() or snapshot.applying()


def _saved(sender: Any, instance: Any, raw: bool = False, **kwargs: Any) -> None:
    if _skip(raw):
        return
    label = sender._meta.label_lower
    if label == "core.auditlog":
        if instance.event_id:
            data = {**instance.payload(), "hash": instance.hash}
            record(instance.event_id, "audit", data=data)
        return
    if label not in live():
        return
    from . import snapshot

    ev = event_id_of(instance)
    if ev:
        record(ev, "upsert", model=label, object_id=str(instance.pk), data=snapshot.serialize([instance])[0])


def _deleted(sender: Any, instance: Any, **kwargs: Any) -> None:
    if _skip() or sender._meta.label_lower not in live():
        return
    ev = event_id_of(instance)
    if ev:
        record(ev, "delete", model=sender._meta.label_lower, object_id=str(instance.pk), data={})


def _m2m(sender: Any, instance: Any, action: str, reverse: bool = False, **kwargs: Any) -> None:
    if reverse or action not in ("post_add", "post_remove", "post_clear"):
        return
    _saved(type(instance), instance)


def connect() -> None:
    post_save.connect(_saved, dispatch_uid="evac_node_saved")
    post_delete.connect(_deleted, dispatch_uid="evac_node_deleted")
    m2m_changed.connect(_m2m, dispatch_uid="evac_node_m2m")
