# SPDX-License-Identifier: AGPL-3.0-or-later
"""Outbound delivery: webhook sink -> outbox jobs -> signed HTTP POST."""
from __future__ import annotations

import json
import time
import uuid

import django.dispatch
import requests
from django.conf import settings
from django.utils import timezone

from apps.core import outbox
from apps.extensions import services as ext
from apps.extensions.models import ExtensionConfig

from .models import DeliveryAttempt, InboundEvent, WebhookEndpoint

KEY = "webhooks"
JOB_KIND = "webhooks.deliver"

#: sent after a verified inbound webhook was stored: ``sender=InboundEvent, inbound=<InboundEvent>``
inbound_webhook = django.dispatch.Signal()


def target_configs(event) -> list[ExtensionConfig]:
    configs = []
    inst = ext.instance_config(KEY)
    if inst is not None and inst.feature_enabled("outbound"):
        configs.append(inst)
    if event is not None:
        row = ext.get_config(KEY, event)
        if row is not None and not row.use_instance and row.feature_enabled("outbound"):
            configs.append(row)
    return configs


def envelope(event_type: str, data, event) -> dict:
    return {"type": event_type, "sent_at": timezone.now().isoformat(), "event": event.slug if event else None,
            "data": data}


def sink(event_type: str, payload, event) -> None:
    """Registered webhook sink: one outbox job per subscribed endpoint."""
    for cfg in target_configs(event):
        for ep in cfg.webhook_endpoints.filter(active=True):
            if not ep.wants(event_type):
                continue
            delivery = str(uuid.uuid4())
            outbox.enqueue(JOB_KIND, {"endpoint": str(ep.pk), "delivery": delivery,
                                      "body": envelope(event_type, payload, event)},
                           event=event, key=f"wh:{ep.pk}:{delivery}")


def post(ep: WebhookEndpoint, body: dict, delivery: str, *, timeout=None, verify=True) -> DeliveryAttempt:
    raw = json.dumps(body, separators=(",", ":"), default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "EVAC-Webhooks/1",
        "X-EVAC-Event": body.get("type", ""),
        "X-EVAC-Delivery": delivery,
        "X-EVAC-Signature": ext.sign(ep.secret, raw),
    }
    cfg = ep.config.settings or {}
    timeout = timeout or cfg.get("timeout_seconds") or getattr(settings, "EVAC_WEBHOOK_TIMEOUT", 5)
    verify = cfg.get("verify_tls", True) if verify else False
    started = time.monotonic()
    attempt = DeliveryAttempt(endpoint=ep, delivery_id=delivery, event_type=body.get("type", ""))
    try:
        r = requests.post(ep.url, data=raw, headers=headers, timeout=timeout, verify=verify, allow_redirects=False)
        attempt.status_code = r.status_code
        attempt.ok = 200 <= r.status_code < 300
        if not attempt.ok:
            attempt.error = f"HTTP {r.status_code}"
    except requests.RequestException as exc:
        attempt.error = f"{type(exc).__name__}: {exc}"[:500]
    attempt.duration_ms = int((time.monotonic() - started) * 1000)
    attempt.save()
    ep.last_delivery_at = timezone.now()
    ep.last_status = "OK" if attempt.ok else attempt.error[:120]
    ep.save(update_fields=["last_delivery_at", "last_status"])
    return attempt


def handle_job(job) -> None:
    ep = WebhookEndpoint.objects.select_related("config").filter(pk=job.payload.get("endpoint")).first()
    if ep is None or not ep.active:
        job.result = {"skipped": "endpoint removed or inactive"}
        return
    attempt = post(ep, job.payload["body"], job.payload["delivery"])
    job.result = {"status": attempt.status_code, "ms": attempt.duration_ms}
    if not attempt.ok:
        raise RuntimeError(attempt.error or "delivery failed")


def store_inbound(config, event_type: str, payload) -> InboundEvent:
    item = InboundEvent.objects.create(config=config, event_type=event_type[:100],
                                       payload=payload if isinstance(payload, dict) else {"value": payload})
    inbound_webhook.send(sender=InboundEvent, inbound=item)
    return item
