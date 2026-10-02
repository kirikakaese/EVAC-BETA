# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import hmac
import json
from unittest import mock

import pytest
import requests

from apps.core.models import OutboxJob
from apps.core.registry import registry
from apps.core.webhooks import emit
from apps.extensions import services
from extensions.webhooks import delivery
from extensions.webhooks.models import DeliveryAttempt, WebhookEndpoint

SPEC = registry.get_extension("webhooks")


def config(event=None, features=None):
    cfg = services.get_or_new(SPEC, event)
    return services.save_config(cfg, settings_values={}, secret_values={},
                                features=features or {"outbound": True, "inbound": True}, enabled=True)


def endpoint(cfg, types=(), name="Receiver"):
    from apps.core import crypto

    return WebhookEndpoint.objects.create(config=cfg, name=name, url="https://hooks.example.org/in",
                                          secret_encrypted=crypto.encrypt("whsec_test"), event_types=list(types))


class Resp:
    def __init__(self, status):
        self.status_code = status


@pytest.mark.django_db(transaction=True)
def test_emit_delivers_signed_payload(event, admin):
    ep = endpoint(config(event), types=["event.state_changed"])
    inst_ep = endpoint(config(None), name="Instance")
    with mock.patch("requests.post", return_value=Resp(204)) as post:
        event.transition("setup", user=admin)
    urls = [c.args[0] for c in post.call_args_list]
    assert urls.count("https://hooks.example.org/in") == 2  # event endpoint + instance endpoint
    call = post.call_args_list[0]
    body = call.kwargs["data"]
    sig = "sha256=" + hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    assert call.kwargs["headers"]["X-EVAC-Signature"] == sig
    payload = json.loads(body)
    assert payload["type"] == "event.state_changed" and payload["data"]["to"] == "setup" and payload["event"] == "demo"
    assert OutboxJob.objects.filter(status="done").count() == 2
    ep.refresh_from_db()
    inst_ep.refresh_from_db()
    assert ep.last_status == "OK" and DeliveryAttempt.objects.filter(ok=True).count() == 2


@pytest.mark.django_db
def test_filters_and_failures(event):
    cfg = config(event)
    endpoint(cfg, types=["member.added"])
    emit("event.updated", {"slug": "demo"}, event=event)
    assert not OutboxJob.objects.filter(kind=delivery.JOB_KIND).exists()
    emit("member.added", {"user": "x"}, event=event)
    job = OutboxJob.objects.get(kind=delivery.JOB_KIND)
    with mock.patch("requests.post", return_value=Resp(500)):
        with pytest.raises(RuntimeError):
            delivery.handle_job(job)
    with mock.patch("requests.post", side_effect=requests.ConnectionError("down")):
        with pytest.raises(RuntimeError):
            delivery.handle_job(job)
    assert DeliveryAttempt.objects.filter(ok=False).count() == 2
    WebhookEndpoint.objects.all().delete()
    delivery.handle_job(job)
    assert job.result == {"skipped": "endpoint removed or inactive"}


@pytest.mark.django_db
def test_outbound_feature_off(event):
    endpoint(config(event, features={"outbound": False, "inbound": True}))
    emit("event.updated", {"slug": "demo"}, event=event)
    assert not OutboxJob.objects.filter(kind=delivery.JOB_KIND).exists()


@pytest.mark.django_db
def test_test_connection(event):
    cfg = config(event)
    assert SPEC.test_connection(cfg).ok  # no endpoints
    endpoint(cfg)
    with mock.patch("requests.post", return_value=Resp(200)):
        assert SPEC.test_connection(cfg).ok
    with mock.patch("requests.post", return_value=Resp(404)):
        result = SPEC.test_connection(cfg)
    assert not result.ok and "HTTP 404" in result.message


@pytest.mark.django_db
def test_inbound_signal(event):
    received = []

    def handler(sender, inbound, **kw):
        received.append(inbound.event_type)

    delivery.inbound_webhook.connect(handler)
    try:
        SPEC.handle_webhook(config(event), {"X-EVAC-Event": "sensor.tripped"}, b"{}", {"a": 1})
    finally:
        delivery.inbound_webhook.disconnect(handler)
    assert received == ["sensor.tripped"]


@pytest.mark.django_db
def test_endpoint_pages(admin_client, event):
    cfg = config(event)
    base = "/e/demo/settings/extensions/webhooks/x/endpoints/"
    r = admin_client.post(base, {"name": "CI", "url": "https://ci.example.org/hook", "active": "on",
                                 "event_types": ["event.updated"]})
    assert r.status_code == 302
    ep = WebhookEndpoint.objects.get(config=cfg)
    page = admin_client.get(base).content.decode()
    assert ep.secret in page and ep.secret not in admin_client.get(base).content.decode()
    assert ep.event_types == ["event.updated"]
    admin_client.post(f"{base}{ep.pk}/delete/")
    assert not WebhookEndpoint.objects.exists()
    services.disconnect(cfg)
    assert admin_client.get(base).status_code == 404


@pytest.mark.django_db
def test_purge(event):
    cfg = config(event)
    endpoint(cfg)
    delivery.store_inbound(cfg, "x", [1, 2])
    services.disconnect(cfg)
    assert not WebhookEndpoint.objects.exists()
