# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-event alarm signing key and signed state messages (ADR-0003, ADR-0034).

Every payload sent to a screen carries a signature over a compact core (event, screen, sequence number, state,
drill, takeover, issue time, content version). Screens keep the event's public key from their evacuation bundle
and accept a message only when the signature checks out and its ``seq`` is newer than the last one they accepted.
That lets a *fallback origin* (secondary node, hardware bridge) deliver alarm state over the LAN without being
trusted for anything else, and a stolen screen cannot forge alarms (it has no private key).

The private key is stored encrypted (``apps.core.crypto``) and leaves the server only through an audit-logged
export for bridges and secondary nodes. Rotation keeps the previous public key valid for a grace period.
"""
from __future__ import annotations

import base64
import json
import time
from datetime import timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from django.db import transaction
from django.utils import timezone

from apps.core import audit, crypto

from .models import EventAlarm

GRACE = timedelta(hours=24)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _raw_public(key: Ed25519PrivateKey) -> str:
    return b64(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def _private(row: EventAlarm) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(unb64(crypto.decrypt(row.private_key_encrypted)))


def ensure(event: Any) -> EventAlarm:
    """The event's alarm row with a key pair (created on first use)."""
    row: EventAlarm = EventAlarm.objects.get_or_create(event=event)[0]
    if not row.public_key:
        with transaction.atomic():
            row = EventAlarm.objects.select_for_update().get(pk=row.pk)
            if not row.public_key:
                key = Ed25519PrivateKey.generate()
                raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                        serialization.NoEncryption())
                row.public_key, row.private_key_encrypted = _raw_public(key), crypto.encrypt(b64(raw))
                row.key_created_at = timezone.now()
                row.save(update_fields=["public_key", "private_key_encrypted", "key_created_at"])
    return row


def public_keys(event: Any) -> list[str]:
    """Keys screens accept now: the current one and, during the grace period, the previous one."""
    row = ensure(event)
    keys = [row.public_key]
    if row.previous_public_key and row.previous_valid_until and row.previous_valid_until > timezone.now():
        keys.append(row.previous_public_key)
    return keys


def rotate(event: Any, *, actor: Any = None, request: Any = None) -> EventAlarm:
    row = ensure(event)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    row.previous_public_key, row.previous_valid_until = row.public_key, timezone.now() + GRACE
    row.public_key, row.private_key_encrypted = _raw_public(key), crypto.encrypt(b64(raw))
    row.key_created_at = timezone.now()
    row.save()
    audit.log(action="evacuation.alarm_key_rotated", actor=actor, event=event, request=request,
              message=f"new key {row.public_key[:8]}…, previous valid until {row.previous_valid_until:%Y-%m-%d %H:%M}")
    return row


def export_private(event: Any, *, actor: Any = None, request: Any = None, purpose: str = "") -> str:
    """The private key for a bridge or secondary node (base64url). Audit-logged; handle like a password."""
    row = ensure(event)
    audit.log(action="evacuation.alarm_key_exported", actor=actor, event=event, request=request,
              message=f"key {row.public_key[:8]}… exported" + (f" for {purpose}" if purpose else ""))
    return crypto.decrypt(row.private_key_encrypted)


def canonical(core: dict[str, Any]) -> str:
    return json.dumps(core, sort_keys=True, separators=(",", ":"))


def sign_core(event: Any, core: dict[str, Any]) -> dict[str, str]:
    row = ensure(event)
    msg = canonical(core)
    return {"kid": row.public_key[:8], "m": msg, "s": b64(_private(row).sign(msg.encode()))}


def sign_payload(event: Any, body: dict[str, Any]) -> dict[str, Any]:
    """Add ``sig`` to a screen payload (see :mod:`feed`)."""
    core = {"e": body.get("event"), "sc": body.get("screen") or "*", "seq": body.get("seq"), "st": body.get("state"),
            "d": bool(body.get("drill")), "t": bool(body.get("takeover")), "ia": int(time.time()), "v": body.get("v")}
    return {**body, "sig": sign_core(event, core)}


def state_message(event: Any) -> dict[str, Any]:
    """The event-wide signed state for fallback origins: event status and every zone status (ADR-0034)."""
    from . import feed, machine, services

    now = timezone.now()
    ev, zones = services.statuses(event)

    def st(s: machine.Status) -> dict[str, Any]:
        c = machine.current(s, now)
        out: dict[str, Any] = {"st": c.state.value, "d": c.drill}
        if c.clear_until is not None:
            out["cu"] = int(c.clear_until.timestamp() * 1000)
        return out

    core = {"e": event.slug, "sc": "*", "seq": feed.current_seq(event), "ia": int(time.time()), "ev": st(ev),
            "z": {z: st(s) for z, s in sorted(zones.items())}, "b": sorted(services.blocked_ids(event))}
    return {"sig": sign_core(event, core)}


def verify(public_keys_b64: list[str], sig: dict[str, str]) -> dict[str, Any] | None:
    """The signed core if any of the keys verifies it, else None (used by tests and secondary nodes)."""
    for k in public_keys_b64:
        try:
            Ed25519PublicKey.from_public_bytes(unb64(k)).verify(unb64(sig["s"]), sig["m"].encode())
        except (InvalidSignature, ValueError, KeyError):
            continue
        core: dict[str, Any] = json.loads(sig["m"])
        return core
    return None
