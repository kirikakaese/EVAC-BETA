# SPDX-License-Identifier: AGPL-3.0-or-later
import json

import pytest

from apps.core.plugins import ConnectionResult
from apps.core.registry import registry
from apps.extensions import services
from apps.extensions.models import ExtensionConfig, InboundDelivery
from conftest import login_2fa

SPEC = registry.get_extension("webhooks")


def _cfg(event=None, enabled=True, **kw):
    cfg = services.get_or_new(SPEC, event)
    return services.save_config(cfg, settings_values=kw.get("settings", {"timeout_seconds": 3}),
                                secret_values=kw.get("secrets", {}), features={"outbound": True, "inbound": True},
                                enabled=enabled, use_instance=kw.get("use_instance", False))


@pytest.mark.django_db
def test_effective_config_resolution(event):
    assert services.effective("webhooks", event) is None
    inst = _cfg(None)
    assert services.effective("webhooks") == inst
    assert services.effective("webhooks", event) is None  # "both" scope: events opt in explicitly
    use = _cfg(event, use_instance=True)
    assert use.use_instance and services.effective("webhooks", event) == inst
    assert services.card_status(SPEC, event) == "instance"
    own = services.save_config(use, settings_values={}, secret_values={}, features={}, enabled=True)
    assert services.effective("webhooks", event) == own and services.card_status(SPEC, event) == "enabled"
    services.save_config(own, settings_values={}, secret_values={}, features={}, enabled=False)
    assert services.effective("webhooks", event) is None and services.card_status(SPEC, event) == "disabled"
    assert services.effective("unknown", event) is None


@pytest.mark.django_db
def test_validation_and_features(event):
    cfg = services.get_or_new(SPEC, event)
    with pytest.raises(services.ExtensionError):
        services.save_config(cfg, settings_values={"timeout_seconds": 999}, secret_values={}, features={},
                             enabled=True)
    cfg = _cfg(event)
    assert cfg.feature_enabled("outbound")
    cfg.features = {"outbound": False}
    assert not cfg.feature_enabled("outbound")
    assert not cfg.feature_enabled("missing")


@pytest.mark.django_db
def test_secrets_encrypted_and_never_rendered(admin_client, event, monkeypatch):
    spec = SPEC.__class__(**{**SPEC.__dict__, "secret_fields": (("api_key", "API key"),)})
    monkeypatch.setitem(registry.extensions, "webhooks", spec)
    r = admin_client.post("/e/demo/settings/extensions/webhooks/", {
        "enabled": "on", "s-timeout_seconds": "4", "s-verify_tls": "on", "secret__api_key": "TOPSECRET",
        "feature__outbound": "on"})
    assert r.status_code == 302
    cfg = ExtensionConfig.objects.get(event=event)
    assert cfg.secret("api_key") == "TOPSECRET" and "TOPSECRET" not in cfg.secrets_encrypted
    assert cfg.settings == {"timeout_seconds": 4, "verify_tls": True}
    assert cfg.features == {"outbound": True, "inbound": False}
    page = admin_client.get("/e/demo/settings/extensions/webhooks/").content.decode()
    assert "TOPSECRET" not in page and "stored" in page
    # blank keeps, clear removes
    admin_client.post("/e/demo/settings/extensions/webhooks/", {"enabled": "on", "s-timeout_seconds": "4"})
    assert ExtensionConfig.objects.get(event=event).secret("api_key") == "TOPSECRET"
    admin_client.post("/e/demo/settings/extensions/webhooks/", {"enabled": "on", "s-timeout_seconds": "4",
                                                                "clear__api_key": "on"})
    assert ExtensionConfig.objects.get(event=event).secret("api_key") == ""
    from apps.core.models import AuditLog

    entry = AuditLog.objects.filter(action="extension.configured").order_by("-id")[2]
    assert "TOPSECRET" not in json.dumps(entry.changes)


@pytest.mark.django_db
def test_test_connection_records_health(admin_client, event, monkeypatch):
    _cfg(event)
    spec = SPEC.__class__(**{**SPEC.__dict__, "test_connection": lambda c: ConnectionResult(False, "refused")})
    monkeypatch.setitem(registry.extensions, "webhooks", spec)
    r = admin_client.post("/e/demo/settings/extensions/webhooks/test/", HTTP_HX_REQUEST="true")
    assert "refused" in r.content.decode()
    cfg = ExtensionConfig.objects.get(event=event)
    assert cfg.health == "error" and cfg.last_error == "refused" and cfg.logs.exists()
    assert services.card_status(spec, event) == "error"

    def boom(c):
        raise RuntimeError("kaputt")

    monkeypatch.setitem(registry.extensions, "webhooks", SPEC.__class__(**{**SPEC.__dict__, "test_connection": boom}))
    r = admin_client.post("/e/demo/settings/extensions/webhooks/test/")
    assert r.status_code == 302
    assert "kaputt" in ExtensionConfig.objects.get(event=event).last_error


@pytest.mark.django_db
def test_inbound_webhook_signature_and_idempotency(event, client):
    cfg = _cfg(event)
    secret = services.regenerate_webhook_secret(cfg)
    url = f"/api/v1/extensions/webhooks/{cfg.pk}/webhook/"
    body = json.dumps({"type": "door.opened", "data": {"door": 3}}).encode()
    assert client.post(url, body, content_type="application/json").status_code == 401
    assert client.post(url, body, content_type="application/json",
                       HTTP_X_EVAC_SIGNATURE="sha256=deadbeef").status_code == 401
    sig = services.sign(secret, body)
    r = client.post(url, body, content_type="application/json", HTTP_X_EVAC_SIGNATURE=sig,
                    HTTP_X_EVAC_DELIVERY="d-1", HTTP_X_EVAC_EVENT="door.opened")
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post(url, body, content_type="application/json", HTTP_X_EVAC_SIGNATURE=sig, HTTP_X_EVAC_DELIVERY="d-1")
    assert r.json()["duplicate"] is True
    assert cfg.inbound_events.count() == 1 and InboundDelivery.objects.count() == 1
    bad = b"not json"
    assert client.post(url, bad, content_type="application/json",
                       HTTP_X_EVAC_SIGNATURE=services.sign(secret, bad)).status_code == 400
    assert client.post(f"/api/v1/extensions/nope/{cfg.pk}/webhook/", body,
                       content_type="application/json").status_code == 404
    services.save_config(cfg, settings_values={}, secret_values={}, features={"inbound": False}, enabled=True)
    r = client.post(url, body, content_type="application/json", HTTP_X_EVAC_SIGNATURE=sig, HTTP_X_EVAC_DELIVERY="d-2")
    assert r.status_code == 403
    services.save_config(cfg, settings_values={}, secret_values={}, features={}, enabled=False)
    assert client.post(url, body, content_type="application/json", HTTP_X_EVAC_SIGNATURE=sig).status_code == 403


@pytest.mark.django_db
def test_pages_and_permissions(client, admin_client, event, member):
    assert admin_client.get("/settings/extensions/").status_code == 200
    assert admin_client.get("/e/demo/settings/extensions/").status_code == 200
    assert admin_client.get("/e/demo/settings/extensions/nope/").status_code == 404
    client.force_login(member)
    assert client.get("/settings/extensions/").status_code == 403
    assert client.get("/e/demo/settings/extensions/").status_code == 403


@pytest.mark.django_db
def test_webhook_secret_shown_once_and_disconnect(admin_client, event):
    cfg = _cfg(event)
    admin_client.post("/e/demo/settings/extensions/webhooks/webhook-secret/")
    page = admin_client.get("/e/demo/settings/extensions/webhooks/").content.decode()
    cfg.refresh_from_db()
    assert cfg.webhook_secret in page
    assert cfg.webhook_secret not in admin_client.get("/e/demo/settings/extensions/webhooks/").content.decode()
    r = admin_client.post("/e/demo/settings/extensions/webhooks/disconnect/")
    assert r.status_code == 302 and not ExtensionConfig.objects.filter(pk=cfg.pk).exists()


@pytest.mark.django_db
def test_module_off_hides_extensions(admin_client, event):
    from apps.core import modules

    modules.set_event(event, "extensions", False)
    assert admin_client.get("/e/demo/settings/extensions/").status_code == 404


@pytest.mark.django_db
def test_instance_level_requires_superuser(client, orga, event):
    login_2fa(client, orga)
    assert client.get("/settings/extensions/webhooks/").status_code == 403
    assert client.get("/e/demo/settings/extensions/webhooks/").status_code == 200
