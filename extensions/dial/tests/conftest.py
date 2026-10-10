# SPDX-License-Identifier: AGPL-3.0-or-later
import hashlib
import hmac
import json
from unittest import mock

import pytest

from apps.core import modules
from apps.core.registry import registry
from apps.extensions import services as ext

BASE = "https://dial.example.org"


class Resp:
    def __init__(self, status=200, data=None, content=b""):
        self.status_code, self._data, self.content = status, data, content

    def json(self):
        if self._data is None:
            raise ValueError
        return self._data

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


WAV = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + bytes(24) + b"data" + bytes(4) + bytes(64)


class FakeDial:
    """Routes ``requests`` calls of the client to canned DIAL answers (overridable per test)."""

    def __init__(self):
        self.calls = []
        self.routes = {
            ("GET", "health/"): (200, {"ok": True, "event": "camp", "pbx": {"ok": True, "backend": "dummy"},
                                       "dect": {"ok": True, "backend": "dummy"}}),
            ("GET", "me/"): (200, {"username": "admin", "service_account": "evac", "memberships": []}),
            ("POST", "emergency/broadcast/"): (201, {"id": 7, "targets": 12, "results": {
                "numbers": [], "channels": ["dummy-1"], "text_broadcast": 3, "error": ""}}),
            ("POST", "messaging/broadcast/"): (201, {"id": 4, "sent_count": 5, "failed_count": 1}),
            ("GET", "phonebook/"): (200, {"event": "camp", "count": 2, "results": [
                {"number": "4300", "number_label": "4300", "name": "Medics", "type": "group",
                 "type_display": "Call group", "description": "First aid", "location": "Tent 3"},
                {"number": "4700", "number_label": "4700–4799", "name": "Trunk", "type": "trunk"}]}),
            ("GET", "events/camp/number-plan/"): (200, {"emergency_numbers": ["112", "110"], "voicemail_number": "9999",
                                                        "echo_test_number": "9003"}),
            ("GET", "emergency/targets/"): (200, {"count": 1, "next": None, "results": [
                {"number": "112", "label": "Medics"},
                {"number": "110", "label": "", "dial_target": "Local/4300@dial-camp"}]}),
            ("GET", "pages/"): (200, {"count": 2, "next": None, "results": [
                {"id": 1, "slug": "wifi", "title": "Wi-Fi", "body": "**SSID** camp",
                 "body_html": "<p><strong>SSID</strong> camp &amp; more</p><ul><li>one</li></ul>", "order": 2,
                 "published": True, "show_on_dashboard": True, "updated_at": "2026-07-01T10:00:00Z"},
                {"id": 2, "slug": "draft", "title": "Draft", "body_html": "", "published": False}]}),
            ("GET", "dect/rfps/"): (200, {"count": 2, "next": None, "results": [
                {"name": "RFP-1", "status": "up", "location": "Gate", "active_calls": 2, "handsets": 4},
                {"name": "RFP-2", "status": "down", "location": "Field"}]}),
            ("GET", "dect/clusters/"): (200, {"count": 1, "next": None, "results": [
                {"cluster_id": 1, "name": "Main", "health": "degraded"}]}),
            ("GET", "ivr/announcements/"): (200, {"count": 1, "next": None, "results": [
                {"id": 1, "extension_number": "4000", "audio": "http://localhost:8000/media/ivr/camp/4000/phone-a.wav"}]}),
            ("GET", "events/camp/members/"): (200, [
                {"user": "alice", "role": "orga"}, {"user": "zed", "role": "user"}, {"user": "bob", "role": "admin"}]),
        }
        self.files = {"/media/ivr/camp/4000/phone-a.wav": WAV}

    def request(self, method, url, params=None, json=None, headers=None, timeout=None, verify=True,
                allow_redirects=False):
        assert url.startswith(BASE + "/api/v1/"), url
        path = url[len(BASE + "/api/v1/"):]
        self.calls.append((method, path, params, json, headers))
        status, data = self.routes.get((method, path), (404, {"detail": "Not found."}))
        if callable(data):
            status, data = data(params, json)
        return Resp(status, data)

    def get(self, url, headers=None, timeout=None, verify=True, stream=False, allow_redirects=False):
        path = url[len(BASE):]
        self.calls.append(("DOWNLOAD", path, None, None, headers))
        if path in self.files:
            return Resp(200, None, self.files[path])
        return Resp(404, None, b"")


@pytest.fixture
def dial():
    fake = FakeDial()
    with mock.patch("extensions.dial.client.requests.request", side_effect=fake.request), \
            mock.patch("extensions.dial.client.requests.get", side_effect=fake.get):
        yield fake


@pytest.fixture
def link(event, db):
    modules.set_instance("evacuation", True)
    cfg = ext.get_or_new(registry.get_extension("dial"), event)
    cfg = ext.save_config(cfg, settings_values={"base_url": BASE, "event": "camp"},
                          secret_values={"token": "dial_secret_token"},
                          features={f.key: True for f in registry.get_extension("dial").features}, enabled=True)
    cfg.secret_raw = ext.regenerate_webhook_secret(cfg)
    return cfg


def sign(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def post_hook(client, link, django_capture_on_commit_callbacks):
    def post(kind, data, *, secret=None, run=True):
        body = json.dumps({"type": kind, "sent_at": "2026-07-01T12:00:00+00:00", "data": data}).encode()
        with django_capture_on_commit_callbacks(execute=run):
            return client.post(f"/api/v1/extensions/dial/{link.pk}/webhook/", data=body,
                               content_type="application/json", HTTP_X_DIAL_EVENT=kind,
                               HTTP_X_DIAL_SIGNATURE=sign(secret or link.secret_raw, body))
    return post
