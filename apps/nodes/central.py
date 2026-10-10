# SPDX-License-Identifier: AGPL-3.0-or-later
"""Central side of venue nodes (ADR-0002, ADR-0036): registration, checkout, check-in, op-log, proxied actions."""
from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from django.core import serializers
from django.db import transaction
from django.utils import timezone

from apps.core import audit

from . import recorder, snapshot
from .models import Checkout, Node, ProxiedAction, ReceivedOp, hash_secret

CODE_TTL = timedelta(hours=24)
TOKEN_PREFIX = "evacn_"
#: proxied actions the node has not picked up after this long are given up (central shows them as expired)
ACTION_TTL = timedelta(minutes=5)


class SyncError(Exception):
    pass


def node_label(node: Node) -> str:
    return node.name


# --------------------------------------------------------------------------------------------- registration
def register(name: str, *, actor: Any = None, request: Any = None) -> tuple[Node, str]:
    """A new node waiting for enrolment. Returns the one-time code (shown once)."""
    code = "-".join(secrets.token_hex(3) for _ in range(3))
    node = Node.objects.create(name=name[:100], code_hash=hash_secret(code), code_expires_at=timezone.now() + CODE_TTL,
                               created_by=actor if getattr(actor, "pk", None) else None)
    audit.log(action="node.registered", actor=actor, target=node, request=request, message=node.name)
    return node, code


def new_code(node: Node, *, actor: Any = None, request: Any = None) -> str:
    code = "-".join(secrets.token_hex(3) for _ in range(3))
    node.code_hash, node.code_expires_at = hash_secret(code), timezone.now() + CODE_TTL
    node.save(update_fields=["code_hash", "code_expires_at"])
    audit.log(action="node.code_issued", actor=actor, target=node, request=request, message=node.name)
    return code


def enrol(code: str, *, sign_public: str, box_public: str, version: str = "", ip: str | None = None) -> tuple[Node,
                                                                                                             str]:
    """A node presents its code and public keys; it gets its token (once). The code is then used up."""
    node = Node.objects.filter(code_hash=hash_secret(code.strip().lower()), revoked_at__isnull=True,
                               code_expires_at__gt=timezone.now()).first()
    if node is None or len(sign_public) < 40 or len(box_public) < 40:
        raise SyncError("unknown or expired enrolment code")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    node.sign_public, node.box_public, node.token_hash = sign_public, box_public, hash_secret(token)
    node.code_hash, node.code_expires_at, node.enrolled_at = "", None, timezone.now()
    node.version, node.last_ip, node.last_seen = version[:40], ip, timezone.now()
    node.save()
    audit.log(action="node.enrolled", target=node, message=f"{node.name} enrolled",
              changes={"sign_public": [None, sign_public[:12] + "…"]})
    return node, token


def revoke(node: Node, *, actor: Any = None, request: Any = None) -> None:
    if open_checkouts(node).exists():
        raise SyncError("check the node's events in first (or force the check-in)")
    node.revoked_at, node.token_hash = timezone.now(), ""
    node.save(update_fields=["revoked_at", "token_hash"])
    audit.log(action="node.revoked", actor=actor, target=node, request=request, message=node.name)


def authenticate(token: str) -> Node | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    return Node.objects.filter(token_hash=hash_secret(token), revoked_at__isnull=True).first()


def open_checkouts(node: Node | None = None) -> Any:
    qs = Checkout.objects.filter(state__in=Checkout.OPEN).select_related("event", "node")
    return qs.filter(node=node) if node is not None else qs


def checkout_of(event: Any) -> Checkout | None:
    return open_checkouts().filter(event=event).first()


# --------------------------------------------------------------------------------------------- checkout
def checkout(event: Any, node: Node, *, actor: Any = None, request: Any = None) -> Checkout:
    if not node.active:
        raise SyncError("the node is not enrolled")
    with transaction.atomic():
        if checkout_of(event) is not None:
            raise SyncError("the event is already checked out")
        co = Checkout.objects.create(event=event, node=node, started_by=actor if getattr(actor, "pk", None) else None)
    audit.log(action="node.checkout", actor=actor, event=event, target=co, request=request,
              message=f"{event.slug} checked out to {node.name}")
    return co


def request_checkin(co: Checkout, *, actor: Any = None, request: Any = None) -> None:
    if co.state != Checkout.State.ACTIVE:
        return
    co.state = Checkout.State.CHECKIN_REQUESTED
    co.save(update_fields=["state"])
    audit.log(action="node.checkin_requested", actor=actor, event=co.event, target=co, request=request,
              message=f"{co.event.slug}: check-in requested from {co.node.name}")


def complete_checkin(co: Checkout, *, final_seq: int, alarm_seq: int = 0) -> Checkout:
    """The node pushed everything up to ``final_seq``; the event is central's again."""
    if co.state not in Checkout.OPEN:
        raise SyncError("not checked out")
    if final_seq > co.applied_seq:
        raise SyncError(f"op-log incomplete: central has {co.applied_seq}, node says {final_seq}")
    _adopt_alarm_seq(co.event, alarm_seq)
    co.state, co.ended_at = Checkout.State.CHECKED_IN, timezone.now()
    co.save(update_fields=["state", "ended_at"])
    audit.log(action="node.checked_in", event=co.event, target=co,
              message=f"{co.event.slug} checked in from {co.node.name} at op-log #{co.applied_seq}")
    return co


def force_checkin(co: Checkout, *, actor: Any = None, request: Any = None, reason: str = "") -> Checkout:
    """The node is lost: central takes the event back at the last op-log position it has (sensitive)."""
    co.state, co.ended_at = Checkout.State.FORCED, timezone.now()
    co.ended_by = actor if getattr(actor, "pk", None) else None
    co.save(update_fields=["state", "ended_at", "ended_by"])
    ProxiedAction.objects.filter(checkout=co, status=ProxiedAction.Status.PENDING).update(
        status=ProxiedAction.Status.EXPIRED, done_at=timezone.now())
    _adopt_alarm_seq(co.event, 0, bump=1000)
    audit.log(action="node.checkin_forced", actor=actor, event=co.event, target=co, request=request,
              message=f"{co.event.slug} taken back from {co.node.name} at op-log #{co.applied_seq}"
                      + (f": {reason}" if reason else ""))
    return co


def _adopt_alarm_seq(event: Any, alarm_seq: int, bump: int = 1) -> None:
    """Screens that followed the node must accept central's next message: move the counter past the node's."""
    from django.apps import apps

    if not apps.is_installed("apps.evacuation"):
        return
    from django.db.models import F

    from apps.evacuation.models import EventAlarm

    EventAlarm.objects.get_or_create(event=event)
    EventAlarm.objects.filter(event=event, seq__lt=alarm_seq).update(seq=alarm_seq)
    EventAlarm.objects.filter(event=event).update(seq=F("seq") + bump)


# --------------------------------------------------------------------------------------------- snapshot
def snapshot_for(co: Checkout) -> dict[str, Any]:
    return snapshot.build(co.event, seed=not co.seeded, box_public=co.node.box_public)


def confirm_snapshot(co: Checkout, version: str, *, seeded: bool) -> None:
    co.snapshot_version, co.last_sync = version[:64], timezone.now()
    if seeded:
        co.seeded = True
    co.save(update_fields=["snapshot_version", "last_sync", "seeded"])


# --------------------------------------------------------------------------------------------- op-log
def apply_oplog(co: Checkout, entries: list[dict[str, Any]]) -> int:
    """Apply a batch from the node, idempotently and in order. Returns the highest contiguous ``seq`` applied."""
    event = co.event
    live = snapshot.live_labels()
    for e in sorted(entries, key=lambda x: int(x.get("seq", 0))):
        seq = int(e.get("seq", 0))
        key = str(e.get("key", ""))[:100]
        if seq <= co.applied_seq or ReceivedOp.objects.filter(key=key).exists():
            continue
        if seq != co.applied_seq + 1:
            break  # a gap: the node sends the missing ones first
        with transaction.atomic(), snapshot.applying_changes():
            _apply_one(co, event, e, live)
            ReceivedOp.objects.create(checkout=co, seq=seq, key=key, kind=str(e["kind"])[:10],
                                      model=str(e.get("model", ""))[:100], object_id=str(e.get("object_id", ""))[:64],
                                      data=e.get("data") or {}, created_at=e.get("created_at") or timezone.now())
            co.applied_seq = seq
            Checkout.objects.filter(pk=co.pk).update(applied_seq=seq, last_sync=timezone.now())
    return co.applied_seq


def _apply_one(co: Checkout, event: Any, e: dict[str, Any], live: set[str]) -> None:
    kind = e.get("kind")
    data = e.get("data") or {}
    if kind == "audit":
        audit.log(action=str(data.get("action", "node.unknown")), event=event, message=str(data.get("message", "")),
                  changes=data.get("changes") or {}, drill=bool(data.get("drill")),
                  scope={**(data.get("scope") or {}), "node": co.node.name, "node_hash": data.get("hash", ""),
                         "node_at": data.get("created_at", "")},
                  imported=data)
        return
    label = str(e.get("model", "")).lower()
    if label not in live:
        raise SyncError(f"{label} is not live state a node may change")
    model = snapshot.model_of(label)
    if kind == "delete":
        obj = model.objects.filter(pk=e.get("object_id")).first()
        if obj is not None:
            if str(recorder.event_id_of(obj)) != str(event.pk):
                raise SyncError("delete outside the event")
            obj.delete()
        return
    if kind != "upsert":
        raise SyncError(f"unknown op {kind!r}")
    if str(data.get("model", "")).lower() != label:
        raise SyncError("row does not match its model")
    for obj in serializers.deserialize("python", [data]):
        if str(recorder.event_id_of(obj.object)) != str(event.pk):
            raise SyncError("row outside the event")
        obj.save()


# --------------------------------------------------------------------------------------------- proxied actions
def proxy(event: Any, kind: str, payload: dict[str, Any], *, actor: Any = None) -> ProxiedAction:
    """Ask the node holding ``event`` to run a live action (it was checked here, it runs there)."""
    co = checkout_of(event)
    if co is None:
        raise SyncError("not checked out")
    act = ProxiedAction.objects.create(checkout=co, kind=kind, payload=payload,
                                       actor=actor if getattr(actor, "pk", None) else None,
                                       actor_repr=str(actor or "")[:200])
    audit.log(action="node.action_proxied", actor=actor, event=event, target=co,
              message=f"{kind} sent to {co.node.name}", changes={"payload": [None, payload]})
    return act


def pending_actions(co: Checkout, after: int = 0) -> list[ProxiedAction]:
    cutoff = timezone.now() - ACTION_TTL
    ProxiedAction.objects.filter(checkout=co, status=ProxiedAction.Status.PENDING, created_at__lt=cutoff).update(
        status=ProxiedAction.Status.EXPIRED, done_at=timezone.now())
    return list(ProxiedAction.objects.filter(checkout=co, status=ProxiedAction.Status.PENDING, id__gt=after))


def action_done(co: Checkout, action_id: int, *, ok: bool, result: dict[str, Any]) -> None:
    ProxiedAction.objects.filter(checkout=co, pk=action_id, status=ProxiedAction.Status.PENDING).update(
        status=ProxiedAction.Status.DONE if ok else ProxiedAction.Status.FAILED, result=result,
        done_at=timezone.now())
