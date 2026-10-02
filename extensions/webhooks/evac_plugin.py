# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generic webhooks: signed outbound deliveries for every registered event type, plus a verified inbound
endpoint. It is the proof extension of the Phase 0 framework (see docs/extensions/webhooks.md)."""
from __future__ import annotations

import uuid

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ConnectionResult, ExtensionFeature, ExtensionSpec, PluginManifest, WebhookResult
from apps.core.registry import Registry

manifest = PluginManifest(key="webhooks", name="Webhooks", version="1.0.0", kind="extension",
                          description="Generic outbound and inbound webhooks.")


def test_connection(config) -> ConnectionResult:
    from . import delivery

    endpoints = list(config.webhook_endpoints.filter(active=True))
    if not endpoints:
        return ConnectionResult(True, str(_("No outbound endpoints yet - add one below. "
                                            "Inbound webhooks need no test.")))
    failed = []
    for ep in endpoints:
        attempt = delivery.post(ep, delivery.envelope("webhook.ping", {"ping": True}, config.event), str(uuid.uuid4()))
        if not attempt.ok:
            failed.append(f"{ep.name}: {attempt.error}")
    if failed:
        return ConnectionResult(False, "; ".join(failed))
    return ConnectionResult(True, str(_("%(n)d endpoint(s) answered the ping.")) % {"n": len(endpoints)})


def handle_webhook(config, headers, body: bytes, payload) -> WebhookResult:
    from . import delivery

    if not config.feature_enabled("inbound"):
        return WebhookResult(403, {"ok": False, "error": "inbound webhooks are switched off"})
    event_type = headers.get("X-EVAC-Event") or (payload.get("type") if isinstance(payload, dict) else "") or ""
    item = delivery.store_inbound(config, event_type, payload)
    return WebhookResult(200, {"ok": True, "id": item.pk})


def purge(config) -> None:
    config.webhook_endpoints.all().delete()
    config.inbound_events.all().delete()


SPEC = ExtensionSpec(
    key="webhooks",
    name="Webhooks",
    description=str(_("Send signed HTTP callbacks for EVAC events to any URL and receive verified webhooks from "
                      "other systems.")),
    version="1.0.0",
    scope="both",
    settings_schema={
        "type": "object",
        "properties": {
            "timeout_seconds": {"type": "integer", "title": "Timeout (seconds)", "minimum": 1, "maximum": 30,
                                "default": 5},
            "verify_tls": {"type": "boolean", "title": "Verify TLS certificates", "default": True},
        },
    },
    features=(
        ExtensionFeature("outbound", str(_("Outbound webhooks")), "webhook",
                         str(_("Deliver EVAC events to the endpoints listed on this page."))),
        ExtensionFeature("inbound", str(_("Inbound webhooks")), "webhook",
                         str(_("Accept signed webhooks at the URL shown on this page."))),
    ),
    inbound_webhooks=True,
    test_connection=test_connection,
    handle_webhook=handle_webhook,
    purge=purge,
    urls="extensions.webhooks.urls",
    docs="extensions/webhooks",
    icon="⇄",
)


def register(r: Registry) -> None:
    from . import delivery

    r.extension(SPEC)
    r.webhook_sink(delivery.sink)
    r.outbox_handler(delivery.JOB_KIND, delivery.handle_job)
