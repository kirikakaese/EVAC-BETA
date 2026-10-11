# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation alarms to staff channels (ADR-0049): opt-in, after the screens, drills marked, ntfy only with a token."""
from unittest import mock

import pytest

from apps.core import alerts, settings_store
from apps.core.models import OutboxJob
from apps.core.registry import registry
from apps.evacuation import services, staff_alerts
from apps.extensions import services as ext
from apps.extensions.models import ExtensionLog
from extensions.notify.tests.test_notify import Resp, configure

from .conftest import tf


@pytest.fixture
def ntfy_calls():
    calls = []

    def fake(method, url, json=None, headers=None, timeout=None, allow_redirects=True):
        calls.append((url, json, headers))
        return Resp(200, {"ok": True})

    with mock.patch("extensions.notify.http.requests.request", side_effect=fake):
        yield calls


def opt_in(event, admin, channels=("ntfy",)):
    settings_store.save("evacuation", "event", str(event.pk), {"staff_alarm_channels": list(channels)},
                        user=admin, event=event)


def change(event, admin, state, capture, **kw):
    with capture(execute=True):
        return services.change(event, state, actor=admin, request=tf(admin), **kw)


def test_off_by_default(event, admin, ntfy_calls, django_capture_on_commit_callbacks):
    configure("ntfy", event)
    change(event, admin, "evacuate", django_capture_on_commit_callbacks)
    assert not OutboxJob.objects.filter(kind=alerts.JOB).exists() and ntfy_calls == []


def test_ntfy_with_a_token_gets_every_state_change(event, admin, ntfy_calls, django_capture_on_commit_callbacks):
    configure("ntfy", event)
    opt_in(event, admin, ("ntfy", "matrix"))  # matrix is not set up: skipped
    change(event, admin, "evacuate", django_capture_on_commit_callbacks, reason="Fire in hall B")
    url, body, headers = ntfy_calls[-1]
    assert headers["Authorization"] == "Bearer tk_ntfy" and body["topic"] == "camp-news"
    assert body["priority"] == 5 and body["tags"] == ["rotating_light"]
    assert "Fire in hall B" in body["message"] and event.name in body["title"]
    assert body["click"].endswith("/e/demo/staff/")
    assert OutboxJob.objects.filter(kind=alerts.JOB).count() == 1
    change(event, admin, "all_clear", django_capture_on_commit_callbacks)
    assert ntfy_calls[-1][1]["priority"] == 3 and ntfy_calls[-1][1]["tags"] == []
    n = len(ntfy_calls)
    change(event, admin, "normal", django_capture_on_commit_callbacks)
    assert len(ntfy_calls) == n  # back to normal after the all clear is not news


def test_drills_are_marked_and_not_max_priority(event, admin, ntfy_calls, django_capture_on_commit_callbacks):
    configure("ntfy", event)
    opt_in(event, admin)
    change(event, admin, "evacuate", django_capture_on_commit_callbacks, drill=True)
    body = ntfy_calls[-1][1]
    assert body["title"].startswith("DRILL: ") and "(DRILL)" in body["message"]
    assert body["priority"] == 4 and body["tags"] == ["warning"]


def test_ntfy_without_a_token_refuses_alarms(event, admin, ntfy_calls, django_capture_on_commit_callbacks):
    cfg = ext.get_or_new(registry.get_extension("ntfy"), event)
    cfg = ext.save_config(cfg, settings_values={"server": "https://ntfy.example.org/", "topic": "open-topic"},
                          secret_values={}, features={}, enabled=True)
    assert not cfg.secret("token")
    opt_in(event, admin)
    change(event, admin, "evacuate", django_capture_on_commit_callbacks)
    assert ntfy_calls == []  # an open topic would let anyone post a fake "Evacuate"
    assert ExtensionLog.objects.filter(config=cfg, level="error", message__icontains="access token").exists()


def test_message_for_zones_and_unknown_states(event, admin, zones):
    entry = mock.Mock(to_state="shelter_in_place", zone_name="North", drill=False, reason="", pk="x1")
    alert = staff_alerts.message(event, entry)
    assert alert.critical and alert.level == "err" and alert.key == "evac:x1" and "North" in alert.title
    entry.to_state = "normal"
    assert staff_alerts.message(event, entry) is None
