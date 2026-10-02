# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit logging helper used across all apps.

Usage::

    from apps.core.audit import log
    log(action="event.state_changed", actor=request.user, target=event, event=event,
        message="Event went live", changes={"state": ["setup", "live"]}, request=request)

``action`` is a dotted ``<area>.<verb>`` string. ``changes`` maps field -> [before, after].
Every row is appended to a SHA-256 hash chain (:mod:`apps.core.hashchain`); :func:`verify_chain`
detects modified, removed or reordered rows.
"""
from __future__ import annotations

import csv
import io
import ipaddress
import json
from collections.abc import Iterable
from typing import Any

from django.db import transaction
from django.utils import timezone

from . import hashchain
from .models import AuditChainHead, AuditLog


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str)) if value is not None else None


def client_ip(request) -> str | None:
    if request is None:
        return None
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    raw = (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR")) or ""
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def log(
    *,
    action: str,
    actor=None,
    target=None,
    event=None,
    message: str = "",
    changes: dict[str, Any] | None = None,
    scope: dict[str, Any] | None = None,
    request=None,
    drill: bool = False,
) -> AuditLog:
    if actor is None and request is not None and getattr(request, "user", None) is not None:
        actor = request.user if request.user.is_authenticated else None
    if event is None and target is not None:
        event = getattr(target, "event", None)
    if event is None and target is not None and target.__class__.__name__ == "Event":
        event = target
    entry = AuditLog(
        created_at=timezone.now(),
        actor_id=getattr(actor, "pk", None) if actor is not None else None,
        actor_repr=(f"{actor} <{getattr(actor, 'email', '')}>" if getattr(actor, "email", "") else str(actor))[:200]
        if actor is not None else "system",
        event_id=getattr(event, "pk", None) if event is not None else None,
        event_repr=(getattr(event, "slug", "") or str(event))[:200] if event is not None else "",
        action=action[:64],
        message=(message or "")[:500],
        changes=_jsonable(changes or {}),
        scope=_jsonable(scope or {}),
        ip_address=client_ip(request),
        drill=drill,
    )
    service = getattr(request, "service_token", None) if request is not None else None
    if service is not None:
        entry.scope = {**entry.scope, "service_token": str(service.pk)}
    if target is not None and getattr(target, "pk", None) is not None:
        entry.target_type = f"{target._meta.app_label}.{target._meta.model_name}"
        entry.target_id = str(target.pk)
        entry.target_repr = str(target)[:300]
    with transaction.atomic():
        head, _ = AuditChainHead.objects.select_for_update().get_or_create(
            pk=1, defaults={"last_hash": hashchain.GENESIS}
        )
        entry.prev_hash = head.last_hash
        entry.hash = hashchain.compute(entry.prev_hash, entry.payload())
        entry.save()
        AuditChainHead.objects.filter(pk=1).update(last_hash=entry.hash, count=head.count + 1)
    return entry


def verify_chain(batch: int = 2000) -> hashchain.VerifyResult:
    """Walk the whole chain in insertion order. Also checks that the head points at the last row."""

    def rows() -> Iterable[tuple[Any, str, str, dict]]:
        last = 0
        while True:
            chunk = list(AuditLog.objects.filter(id__gt=last).order_by("id")[:batch])
            if not chunk:
                return
            for row in chunk:
                yield row.id, row.prev_hash, row.hash, row.payload()
            last = chunk[-1].id

    result = hashchain.verify(rows())
    if not result.ok:
        return result
    head = AuditChainHead.objects.filter(pk=1).first()
    last = AuditLog.objects.order_by("-id").first()
    if last is not None and (head is None or head.last_hash != last.hash):
        return hashchain.VerifyResult(False, result.checked, last.id, "chain head does not match the newest row "
                                                                       "(rows appended outside EVAC or truncated)")
    return result


EXPORT_FIELDS = ("id", "created_at", "actor_repr", "event_repr", "action", "target_type", "target_id",
                 "target_repr", "scope", "message", "changes", "ip_address", "drill", "prev_hash", "hash")


def export_rows(qs) -> list[dict[str, Any]]:
    out = []
    for row in qs.order_by("id"):
        item = {f: getattr(row, f) for f in EXPORT_FIELDS}
        item["created_at"] = row.created_at.isoformat()
        out.append(item)
    return out


def export_csv(qs) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for item in export_rows(qs):
        item["scope"] = json.dumps(item["scope"], sort_keys=True)
        item["changes"] = json.dumps(item["changes"], sort_keys=True)
        writer.writerow(item)
    return buf.getvalue()
