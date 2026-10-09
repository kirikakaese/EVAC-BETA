# SPDX-License-Identifier: AGPL-3.0-or-later
"""Web Push (ADR-0021): VAPID (RFC 8292) and message encryption (RFC 8291, aes128gcm), with `cryptography` only.

Every in-app notification (``apps.core.notify.notify``) is also pushed to the user's subscribed browsers (the staff
PWA). Each push is an outbox job, so a push service that is down is retried; a subscription the push service
reports as gone (404/410) is deleted.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import time
from typing import Any
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import hashes, hmac, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import crypto

JOB_KIND = "webpush.send"
RECORD_SIZE = 4096
TTL = {"err": 600, "warn": 3600, "ok": 3600, "info": 3600}
URGENCY = {"err": "high", "warn": "normal", "ok": "low", "info": "normal"}


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _public_bytes(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


# ------------------------------------------------------------------ VAPID
def vapid_key():
    """The instance key pair (created on first use)."""
    from .models import VapidKey

    row = VapidKey.objects.first()
    if row is None:
        with transaction.atomic():
            row = VapidKey.objects.select_for_update().first()
            if row is None:
                private = ec.generate_private_key(ec.SECP256R1())
                pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()).decode()
                row = VapidKey.objects.create(private_key_encrypted=crypto.encrypt(pem),
                                              public_key=b64u(_public_bytes(private.public_key())))
    return row


def public_key() -> str:
    return vapid_key().public_key


def _private_key() -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(crypto.decrypt(vapid_key().private_key_encrypted).encode(), None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    return key


def vapid_header(endpoint: str, *, now: int | None = None) -> str:
    """``Authorization: vapid t=<JWT>, k=<public key>`` for the push service of ``endpoint`` (ES256)."""
    parts = urlsplit(endpoint)
    exp = (now or int(time.time())) + 12 * 3600
    subject = getattr(settings, "EVAC_VAPID_SUBJECT", "") or f"mailto:{settings.DEFAULT_FROM_EMAIL}"
    header = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    claims = b64u(json.dumps({"aud": f"{parts.scheme}://{parts.netloc}", "exp": exp, "sub": subject},
                             separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode()
    r, s = decode_dss_signature(_private_key().sign(signing_input, ec.ECDSA(hashes.SHA256())))
    signature = b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={header}.{claims}.{signature}, k={public_key()}"


# ------------------------------------------------------------------ RFC 8291
def _extract(salt: bytes, ikm: bytes) -> bytes:
    """HKDF-Extract (RFC 5869): HMAC-SHA-256(salt, IKM)."""
    h = hmac.HMAC(salt, hashes.SHA256())
    h.update(ikm)
    return h.finalize()


def encrypt(payload: bytes, p256dh: str, auth: str, *, salt: bytes | None = None,
            server_key: ec.EllipticCurvePrivateKey | None = None) -> bytes:
    """Encrypt ``payload`` for a subscription (single aes128gcm record)."""
    ua_public_bytes = b64u_decode(p256dh)
    ua_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public_bytes)
    server_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_public_bytes = _public_bytes(server_key.public_key())
    shared = server_key.exchange(ec.ECDH(), ua_public)
    ikm = HKDF(hashes.SHA256(), 32, salt=b64u_decode(auth),
               info=b"WebPush: info\x00" + ua_public_bytes + as_public_bytes).derive(shared)
    salt = salt or os.urandom(16)
    prk = _extract(salt, ikm)
    cek = HKDFExpand(hashes.SHA256(), 16, info=b"Content-Encoding: aes128gcm\x00").derive(prk)
    nonce = HKDFExpand(hashes.SHA256(), 12, info=b"Content-Encoding: nonce\x00").derive(prk)
    if len(payload) > RECORD_SIZE - 17 - 86:
        raise ValueError("push payload too large")
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + struct.pack("!IB", RECORD_SIZE, len(as_public_bytes)) + as_public_bytes + body


# ------------------------------------------------------------------ sending
class Gone(Exception):
    """The push service says the subscription no longer exists."""


def send(sub, message: dict[str, Any], *, ttl: int = 3600, urgency: str = "normal") -> int:
    """POST one push message; returns the HTTP status. Raises on errors worth retrying."""
    body = encrypt(json.dumps(message, separators=(",", ":")).encode(), sub.p256dh, sub.auth)
    headers = {"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(ttl),
               "Urgency": urgency, "Authorization": vapid_header(sub.endpoint)}
    if message.get("tag"):
        headers["Topic"] = str(message["tag"])[:32]
    try:
        r = requests.post(sub.endpoint, data=body, headers=headers, timeout=10)
    except requests.RequestException as exc:
        raise ConnectionError(f"{type(exc).__name__}: push service not reachable") from None
    if r.status_code in (404, 410):
        raise Gone
    if r.status_code == 429 or r.status_code >= 500:
        raise ConnectionError(f"push service answered HTTP {r.status_code}")
    if r.status_code >= 400:
        raise ValueError(f"push service refused the message: HTTP {r.status_code} {r.text[:200]}")
    return r.status_code


def fan_out(notifications) -> int:
    """Queue a push for every subscribed browser of the notified users (called by ``notify``)."""
    from . import outbox
    from .models import PushSubscription

    by_user: dict[Any, list] = {}
    for n in notifications:
        by_user.setdefault(n.user_id, []).append(n)
    if not by_user:
        return 0
    count = 0
    for sub in PushSubscription.objects.filter(user_id__in=by_user):
        for n in by_user[sub.user_id]:
            outbox.enqueue(JOB_KIND, {"subscription": sub.pk, "notification": n.pk}, event=n.event,
                           key=f"push:{sub.pk}:{n.pk}")
            count += 1
    return count


def message_for(n) -> dict[str, Any]:
    from django.urls import reverse

    return {"title": n.title, "body": n.body[:500], "url": n.url or reverse("core:notifications"),
            "level": n.level, "tag": f"evac-{n.pk}", "event": n.event.slug if n.event_id else ""}


def handle_job(job) -> None:
    """Outbox handler: deliver one notification to one browser."""
    from .models import Notification, PushSubscription

    sub = PushSubscription.objects.filter(pk=job.payload["subscription"]).first()
    n = Notification.objects.select_related("event").filter(pk=job.payload["notification"]).first()
    if sub is None or n is None:
        job.result = {"skipped": "subscription or notification gone"}
        return
    try:
        status = send(sub, message_for(n), ttl=TTL.get(n.level, 3600), urgency=URGENCY.get(n.level, "normal"))
    except Gone:
        sub.delete()
        job.result = {"removed": "the push service no longer knows this browser"}
        return
    except ValueError as exc:
        PushSubscription.objects.filter(pk=sub.pk).update(failures=sub.failures + 1)
        job.result = {"refused": str(exc)}
        return
    PushSubscription.objects.filter(pk=sub.pk).update(last_success_at=timezone.now(), failures=0)
    job.result = {"status": status}


def subscribe(user, data: dict[str, Any], user_agent: str = ""):
    """Store a ``PushSubscription.toJSON()`` from the browser (re-subscribing moves it to ``user``)."""
    from .models import PushSubscription

    endpoint = str(data.get("endpoint") or "")
    keys = data.get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or ""), str(keys.get("auth") or "")
    if not endpoint.startswith("https://") or len(endpoint) > 800:
        raise ValueError("endpoint must be an https URL")
    try:
        if len(b64u_decode(p256dh)) != 65 or len(b64u_decode(auth)) != 16:
            raise ValueError
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b64u_decode(p256dh))
    except (ValueError, TypeError):
        raise ValueError("invalid subscription keys") from None
    sub, _created = PushSubscription.objects.update_or_create(
        endpoint=endpoint, defaults={"user": user, "p256dh": p256dh, "auth": auth, "user_agent": user_agent[:300],
                                     "failures": 0})
    return sub
