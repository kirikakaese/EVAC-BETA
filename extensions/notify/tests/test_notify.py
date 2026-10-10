# SPDX-License-Identifier: AGPL-3.0-or-later
from unittest import mock

import pytest
import requests
from django.core import mail

from apps.announcements import services as ann_services
from apps.announcements.models import Announcement, Delivery, Level
from apps.core.a11y import audit_url
from apps.core.models import OutboxJob
from apps.core.registry import registry
from apps.extensions import services as ext
from apps.extensions.models import ExtensionLog
from extensions.notify import channels
from extensions.notify.http import Rejected, Temporary, call

SETTINGS = {
    "email": ({"recipients": ["ops@example.org", "desk@example.org"], "subject_prefix": "[Camp]"}, {}),
    "ntfy": ({"server": "https://ntfy.example.org/", "topic": "camp-news"}, {"token": "tk_ntfy"}),
    "matrix": ({"homeserver": "https://matrix.example.org", "room_id": "!room:example.org"},
               {"access_token": "syt_matrix"}),
    "telegram": ({"chat_id": "-100123", "api_base": "https://tg.example.org"}, {"bot_token": "123:SECRET"}),
    "mastodon": ({"instance": "https://social.example.org", "visibility": "unlisted", "hashtag": "camp"},
                 {"access_token": "masto_tok"}),
}


class Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text

    def json(self):
        if self._data is None:
            raise ValueError
        return self._data


def configure(key, event=None, **override):
    values, secrets = SETTINGS[key]
    cfg = ext.get_or_new(registry.get_extension(key), event)
    return ext.save_config(cfg, settings_values={**values, **override}, secret_values=secrets, features={},
                           enabled=True)


@pytest.fixture
def levels(event):
    ann_services.ensure_defaults(event)
    return {lv.key: lv for lv in Level.objects.filter(event=event)}


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    def call_(fn, *args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return fn(*args, **kwargs)
    return call_


def tf(user):
    """A two-factor verified request (emergency announcements need one)."""
    from django.test import RequestFactory

    from apps.accounts.twofactor import SESSION_KEY

    request = RequestFactory().get("/")
    request.user, request.session = user, {SESSION_KEY: "2026-01-01T00:00:00"}
    return request


def publish(admin, event, level, channels_, run, **kw):
    a = Announcement(event=event, level=level, title=kw.pop("title", "Storm warning"),
                     body=kw.pop("body", "Thunderstorm at 18:00. Leave the field."), channels=channels_, **kw)
    ann_services.save_draft(a, actor=admin)
    run(ann_services.submit, a, actor=admin, request=tf(admin))
    return {d.channel: d for d in a.deliveries.all()}


def test_channels_appear_only_where_switched_on(event, admin):
    assert not {"email", "ntfy", "matrix", "telegram", "mastodon"} & set(ann_services.available_channels(event))
    configure("ntfy")  # instance-wide: an instance-only setup applies to events that link it
    cfg = ext.get_or_new(registry.get_extension("ntfy"), event)
    ext.save_config(cfg, settings_values={}, secret_values={}, features={}, enabled=True, use_instance=True)
    configure("telegram", event)
    available = ann_services.available_channels(event)
    assert "ntfy" in available and "telegram" in available and "matrix" not in available
    spec = registry.notification_channels["mastodon"]
    assert spec.max_length == 500 and spec.module == "announcements"


def test_all_channels_deliver(admin, event, levels, run, settings):
    settings.EVAC_PUBLIC_URL = "https://evac.example.org"
    for key in SETTINGS:
        configure(key, event)
    calls = []

    def fake(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        if "mastodon" in url or "social" in url:
            return Resp(200, {"url": "https://social.example.org/@camp/1"})
        return Resp(200, {"ok": True})

    with mock.patch("extensions.notify.http.requests.request", side_effect=fake):
        report = publish(admin, event, levels["emergency"], list(SETTINGS), run,
                         channel_texts={"mastodon": "Storm! Leave the field. #camp"})
    assert {k: d.status for k, d in report.items()} == dict.fromkeys(SETTINGS, "sent")
    by_host = {u.split("/")[2]: (m, u, j, h) for m, u, j, h in calls}
    # ntfy: highest priority for emergencies, token, click link
    _m, url, body, headers = by_host["ntfy.example.org"]
    assert url == "https://ntfy.example.org" and body["priority"] == 5 and body["topic"] == "camp-news"
    assert body["title"] == "Emergency: Storm warning" and headers["Authorization"] == "Bearer tk_ntfy"
    assert body["click"].startswith("https://evac.example.org/e/demo/announcements/")
    # Matrix: idempotent transaction id, HTML with the level colour
    m, url, body, headers = by_host["matrix.example.org"]
    assert m == "PUT" and url.endswith(f"/rooms/%21room%3Aexample.org/send/m.room.message/{report['matrix'].pk}")
    assert "Leave the field." in body["formatted_body"] and levels["emergency"].colour in body["formatted_body"]
    # Telegram: HTML, escaped, notifications on
    _m, url, body, _h = by_host["tg.example.org"]
    assert url == "https://tg.example.org/bot123:SECRET/sendMessage" and body["parse_mode"] == "HTML"
    assert body["text"].startswith("<b>Emergency: Storm warning</b>") and not body["disable_notification"]
    # Mastodon: own text, idempotency key, visibility
    _m, url, body, headers = by_host["social.example.org"]
    assert body == {"status": "Storm! Leave the field. #camp", "visibility": "unlisted"}
    assert headers["Idempotency-Key"] == str(report["mastodon"].pk)
    assert report["mastodon"].detail == "https://social.example.org/@camp/1"
    # e-mail: BCC to the list, subject with prefix and level
    msg = mail.outbox[-1]
    assert msg.subject == "[Camp] Emergency: Storm warning" and sorted(msg.bcc) == ["desk@example.org",
                                                                                      "ops@example.org"]
    assert msg.extra_headers["Importance"] == "high" and report["email"].recipients == 2


def test_refusal_fails_without_retry_and_logs(admin, event, levels, run):
    cfg = configure("telegram", event)
    with mock.patch("extensions.notify.http.requests.request",
                    return_value=Resp(401, {"ok": False, "description": "Unauthorized"})):
        report = publish(admin, event, levels["info"], ["telegram"], run)
    d = report["telegram"]
    assert d.status == "failed" and d.detail == "HTTP 401: Unauthorized"
    assert "SECRET" not in d.detail
    assert ExtensionLog.objects.filter(config=cfg, level="error").exists()
    assert OutboxJob.objects.get(kind="announcements.deliver").status == "done"


def test_network_error_is_retried_without_leaking_the_url(admin, event, levels, run):
    configure("telegram", event)
    with mock.patch("extensions.notify.http.requests.request",
                    side_effect=requests.ConnectionError("https://tg.example.org/bot123:SECRET/sendMessage")):
        report = publish(admin, event, levels["info"], ["telegram"], run)
    d = report["telegram"]
    assert d.status == "failed" and "SECRET" not in d.detail and "ConnectionError" in d.detail
    job = OutboxJob.objects.get(kind="announcements.deliver")
    assert job.status != "done" and job.attempts == 1 and "SECRET" not in job.last_error
    # the retry succeeds: the delivery report shows it as sent
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(200, {"ok": True})):
        from apps.core import outbox

        outbox.deliver(job)
    d.refresh_from_db()
    assert d.status == "sent" and d.attempts == 2


def test_http_helper():
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(503, text="down")):
        with pytest.raises(Temporary):
            call("GET", "https://x.example.org")
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(429, {})):
        with pytest.raises(Temporary):
            call("GET", "https://x.example.org")
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(400, None, "bad thing")):
        with pytest.raises(Rejected, match="bad thing"):
            call("GET", "https://x.example.org")
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(403, ["x"])):
        with pytest.raises(Rejected, match="x"):
            call("GET", "https://x.example.org")
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(204)):
        assert call("GET", "https://x.example.org") == {}


def test_skipped_when_switched_off_after_publishing(admin, event, levels, run):
    cfg = configure("ntfy", event)
    a = Announcement(event=event, level=levels["info"], title="Hi", channels=["ntfy"])
    ann_services.save_draft(a, actor=admin)
    cfg.enabled = False
    cfg.save()
    d = Delivery.objects.create(announcement=a, channel="ntfy", occurrence=a.starts_at)
    ann_services.deliver(OutboxJob(payload={"delivery": str(d.pk)}))
    d.refresh_from_db()
    assert d.status == "skipped"


def test_email_staff_and_no_recipients(admin, event, levels, run):
    configure("email", event, recipients=[], to_staff=False)
    report = publish(admin, event, levels["info"], ["email"], run)
    assert report["email"].status == "skipped"
    configure("email", event, recipients=[], to_staff=True)
    report = publish(admin, event, levels["info"], ["email"], run, title="Second")
    assert report["email"].status == "sent" and "root@example.org" in mail.outbox[-1].bcc


def test_texts_and_levels(admin, event, levels):
    a = Announcement(event=event, level=levels["info"], title="T" * 600, body="")
    assert len(ann_services.text_for(a, "mastodon", 500)) == 500
    assert ann_services.text_for(a, "mastodon", 500).endswith("…")
    assert channels.urgency(a) == "low"
    a.level = levels["important"]
    assert channels.urgency(a) == "normal"
    a.level = levels["urgent"]
    assert channels.urgency(a) == "high"
    # an own text longer than the channel allows is refused
    configure("mastodon", event)
    b = Announcement(event=event, level=levels["info"], title="x", channels=["mastodon"],
                     channel_texts={"mastodon": "y" * 501})
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        ann_services.save_draft(b, actor=admin)
    b.channel_texts = {"nope": "y"}
    with pytest.raises(ValidationError):
        ann_services.save_draft(b, actor=admin)


def test_ntfy_and_mastodon_default_texts(admin, event, levels, run, settings):
    settings.EVAC_PUBLIC_URL = ""
    configure("ntfy", event)
    configure("mastodon", event)
    sent = []
    with mock.patch("extensions.notify.http.requests.request",
                    side_effect=lambda m, u, json=None, headers=None, timeout=None: sent.append(json) or Resp(200, {})):
        publish(admin, event, levels["info"], ["ntfy", "mastodon"], run, title="Bar open", body="Until 2 am")
    ntfy = next(b for b in sent if "topic" in b)
    toot = next(b for b in sent if "status" in b)
    assert ntfy["message"] == "Until 2 am" and ntfy["priority"] == 2 and "click" not in ntfy
    assert toot["status"] == "Bar open\n\nUntil 2 am\n\n#camp"


@pytest.mark.parametrize("key,answer,expected", [
    ("telegram", {"ok": True, "result": {"username": "camp_bot"}}, "Bot @camp_bot is ready."),
    ("matrix", {"user_id": "@evac:example.org"}, "Signed in as @evac:example.org."),
    ("mastodon", {"acct": "camp"}, "Signed in as @camp."),
    ("ntfy", {}, "A test message (lowest priority) was published."),
])
def test_test_connection(event, key, answer, expected):
    cfg = configure(key, event)
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(200, answer)):
        result = registry.get_extension(key).test_connection(cfg)
    assert result.ok and result.message == expected
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(401, {"error": "nope"})):
        result = registry.get_extension(key).test_connection(cfg)
    assert not result.ok and "401" in result.message


def test_email_test_connection(event):
    cfg = configure("email", event)
    result = registry.get_extension("email").test_connection(cfg)
    assert result.ok and "2 fixed recipients" in result.message
    with mock.patch("extensions.notify.channels.mail.get_connection", side_effect=OSError("refused")):
        result = registry.get_extension("email").test_connection(cfg)
    assert not result.ok and "refused" in result.message


def test_settings_pages(admin_client, event):
    for key in SETTINGS:
        url = f"/e/demo/settings/extensions/{key}/"
        assert admin_client.get(url).status_code == 200, url
        assert audit_url(admin_client, url) == [], url
    r = admin_client.post("/e/demo/settings/extensions/ntfy/", {"enabled": "on", "s_topic": "bad topic!"})
    assert r.status_code in (200, 302)
    assert not ext.effective("ntfy", event)  # invalid topic: nothing saved


def test_composer_offers_channel_texts(admin_client, event, levels):
    configure("mastodon", event)
    configure("matrix", event)
    page = admin_client.get("/e/demo/announcements/new/")
    form = page.context["form"]
    assert "text_mastodon" in form.fields and form.fields["text_mastodon"].max_length == 500
    assert "text_email" not in form.fields
    r = admin_client.post("/e/demo/announcements/new/", {
        "level": levels["info"].pk, "title": "Bar open", "body": "", "short": "", "channels": ["mastodon"],
        "all_screens": "on", "text_mastodon": "The bar is open! #camp", "action": "draft"})
    assert r.status_code == 302
    assert Announcement.objects.get().channel_texts == {"mastodon": "The bar is open! #camp"}


# ------------------------------------------------------------------ staff alerts (ADR-0039)
def test_staff_alerts(event, settings):
    from apps.core import alerts
    from apps.core.plugins import Alert

    settings.EVAC_PUBLIC_URL = "https://evac.example.org"
    for key in SETTINGS:
        configure(key, event)
    assert set(alerts.channels(event)) >= {"email", "ntfy", "matrix", "telegram"}
    assert "mastodon" not in alerts.channels(event)  # public: never for staff alerts
    calls = []

    def fake(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json))
        return Resp(200, {"ok": True})

    a = Alert(title="Hall A is full", body="Please use Hall B.", level="warn", url="/e/demo/crowd/", key="k1")
    with mock.patch("extensions.notify.http.requests.request", side_effect=fake):
        for key in ("ntfy", "matrix", "telegram", "email"):
            res = registry.notification_channels[key].alert(event, a)
            assert res["recipients"] >= 1, key
    hosts = {u.split("/")[2]: (m, u, j) for m, u, j in calls}
    assert hosts["ntfy.example.org"][2]["priority"] == 4
    assert hosts["ntfy.example.org"][2]["click"] == "https://evac.example.org/e/demo/crowd/"
    matrix = hosts["matrix.example.org"]
    assert matrix[0] == "PUT" and "Hall A is full" in matrix[2]["body"]
    assert hosts["tg.example.org"][2]["disable_notification"] is False
    assert mail.outbox[-1].subject == "[Camp] Hall A is full" and mail.outbox[-1].bcc
    # a retried alert posts with the same Matrix transaction id
    with mock.patch("extensions.notify.http.requests.request", side_effect=fake):
        registry.notification_channels["matrix"].alert(event, a)
    assert calls[-1][1] == matrix[1]
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(401, text="no")):
        assert registry.notification_channels["ntfy"].alert(event, a)["status"] == "failed"
    assert channels.alerter("mastodon") is None


def test_alert_outbox_job(event, settings, django_capture_on_commit_callbacks):
    from apps.core import alerts, outbox
    from apps.core.plugins import Alert

    configure("ntfy", event)
    assert alerts.enqueue(event, ["ntfy", "unknown"], Alert(title="x", key="same")) == 1
    assert alerts.enqueue(event, ["ntfy"], Alert(title="x", key="same")) == 1
    job = OutboxJob.objects.get(kind=alerts.JOB)
    with mock.patch("extensions.notify.http.requests.request", return_value=Resp(200, {})), \
            django_capture_on_commit_callbacks(execute=True):
        assert outbox.deliver(job)
    assert job.result["recipients"] == 1
    job2 = OutboxJob(kind=alerts.JOB, payload={"channel": "gone"}, event=event)
    alerts.handle_job(job2)
    assert job2.result == {"skipped": "channel gone"}
    cfg = ext.get_or_new(registry.get_extension("ntfy"), event)
    cfg.enabled = False
    cfg.save()
    assert alerts.channels(event) == {} or "ntfy" not in alerts.channels(event)
