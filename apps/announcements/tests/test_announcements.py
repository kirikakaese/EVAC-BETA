# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken, User
from apps.announcements import services
from apps.announcements.models import Announcement, Delivery, Level, Template
from apps.content import services as content
from apps.core import modules, settings_store
from apps.core.a11y import audit_url
from apps.core.models import AuditLog, Notification, OutboxJob
from apps.events import services as event_services
from apps.playlists import services as playlists
from apps.screens import services as screen_services
from apps.screens.models import ScreenGroup
from conftest import login_2fa


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    """Run ``fn`` and the outbox deliveries it queues (Celery is eager in tests)."""
    def call(fn, *args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return fn(*args, **kwargs)
    return call


@pytest.fixture
def levels(event):
    services.ensure_defaults(event)
    return {lv.key: lv for lv in Level.objects.filter(event=event)}


@pytest.fixture
def paired(client, admin, event):
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    screen = screen_services.pair(event, data["code"], actor=admin, name="Foyer")
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    return screen, token


@pytest.fixture
def helpdesk(event, role):
    u = User.objects.create_user(email="desk@example.org", password="pw-desk-123456")
    event_services.assign_role(event, u, role("helpdesk"))
    return u


@pytest.fixture
def control(event, role):
    u = User.objects.create_user(email="control@example.org", password="pw-control-1234")
    event_services.assign_role(event, u, role("control-room"))
    return u


def tf(user):
    """A request of ``user`` in a two-factor verified session (built-in staff roles need one)."""
    from django.test import RequestFactory

    from apps.accounts.twofactor import SESSION_KEY

    request = RequestFactory().get("/")
    request.user, request.session = user, {SESSION_KEY: "2026-01-01T00:00:00"}
    return request


def ann(event, level, **kw):
    kw.setdefault("title", "Doors open")
    kw.setdefault("channels", [services.SCREENS, services.STAFF])
    return Announcement(event=event, level=level, **kw)


# ------------------------------------------------------------------ texts and defaults
def test_defaults_are_created_once(event):
    services.ensure_defaults(event)
    services.ensure_defaults(event)
    assert sorted(Level.objects.filter(event=event).values_list("key", flat=True)) == [
        "emergency", "important", "info", "urgent"]
    assert Template.objects.filter(event=event, builtin=True).count() == len(services.DEFAULT_TEMPLATES)
    emergency = Level.objects.get(event=event, key="emergency")
    assert emergency.screen_priority == 500 and str(emergency) == "Emergency"
    assert Level.objects.get(event=event, key="urgent").screen_priority == 0
    assert Level(display="takeover").screen_priority == 250


def test_template_variables_and_rendering(event, levels):
    tpl = Template.objects.get(event=event, name="Lost child")
    assert services.variables_in(tpl.title, tpl.body, tpl.short) == ["description", "desk"]
    assert services.variables_in("{{ event.name }} {{x}} {{x}}") == ["x"]
    a = Announcement(event=event)
    services.apply_template(a, tpl, {"description": "red cap, 6 years", "desk": "the info point"})
    assert a.level.key == "urgent" and a.template == tpl
    assert a.body == "We are looking for a child: red cap, 6 years. Please contact the info point."
    assert services.render_text("{{event.name}}: {{missing}}", {}, event) == "Demo Camp: {{missing}}"
    assert a.short_text.startswith("Lost child: red cap") and a.text == a.body
    assert Announcement(title="T").short_text == "T" and Announcement(title="T").text == "T"


# ------------------------------------------------------------------ workflow
def test_publish_directly_delivers_through_the_outbox(admin, event, levels, paired, run):
    a = services.save_draft(ann(event, levels["important"]), actor=admin)
    assert a.status == "draft" and a.created_by == admin
    run(services.submit, a, actor=admin)
    a.refresh_from_db()
    assert a.status == "live" and a.published_at and a.last_occurrence == a.starts_at
    report = {d.channel: d for d in a.deliveries.all()}
    assert report["screens"].status == "sent" and report["screens"].recipients == 1
    assert report["staff"].status == "sent" and report["staff"].recipients >= 1
    assert Notification.objects.filter(title__startswith="Important: Doors open").exists()
    assert OutboxJob.objects.filter(kind="announcements.deliver").count() == 2
    assert AuditLog.objects.filter(action="announcement.published").exists()
    # publishing the same occurrence again creates no new delivery
    services.publish(a, occurrence=a.starts_at)
    assert a.deliveries.count() == 2


def test_validation(admin, event, levels):
    with pytest.raises(ValidationError):
        services.save_draft(ann(event, levels["info"], title=" "), actor=admin)
    now = timezone.now()
    with pytest.raises(ValidationError):
        services.save_draft(ann(event, levels["info"], starts_at=now, ends_at=now), actor=admin)
    with pytest.raises(ValidationError):
        services.save_draft(ann(event, levels["info"], recurrence="daily"), actor=admin)
    with pytest.raises(ValidationError):
        services.save_draft(ann(event, levels["info"], channels=["carrier-pigeon"]), actor=admin)
    with pytest.raises(ValidationError):
        services.save_draft(ann(event, levels["info"], channels=[]), actor=admin)


def test_approval_four_eyes(event, levels, helpdesk, control, admin, run):
    a = services.save_draft(ann(event, levels["important"]), actor=helpdesk)
    run(services.submit, a, actor=helpdesk)
    assert a.status == "pending" and a.submitted_at
    assert Notification.objects.filter(user=control, title="Announcement waiting for approval").exists()
    with pytest.raises(PermissionDenied):
        services.approve(a, actor=helpdesk)
    with pytest.raises(ValidationError):
        services.submit(a, actor=helpdesk)
    run(services.approve, a, actor=control, note="ok", request=tf(control))
    a.refresh_from_db()
    assert a.status == "live" and a.decided_by == control and a.decision_note == "ok"
    assert Notification.objects.filter(user=helpdesk, title="Your announcement was approved").exists()
    with pytest.raises(ValidationError):
        services.approve(a, actor=control, request=tf(control))


def test_reject_edit_and_resubmit(event, levels, helpdesk, control):
    a = services.save_draft(ann(event, levels["info"]), actor=helpdesk)
    services.submit(a, actor=helpdesk)
    services.reject(a, actor=control, note="typo", request=tf(control))
    assert a.status == "rejected"
    assert Notification.objects.filter(user=helpdesk, title="Your announcement was rejected", body__contains="typo")
    with pytest.raises(ValidationError):
        services.reject(a, actor=control, request=tf(control))
    a.title = "Doors open at 18:00"
    services.save_draft(a, actor=helpdesk)
    assert a.status == "draft"
    services.delete_draft(a, actor=helpdesk)
    assert not Announcement.objects.filter(pk=a.pk).exists()


def test_approval_required_setting_and_level(admin, event, levels, control):
    settings_store.save("announcements", "event", str(event.pk), {"approval_required": True}, user=admin,
                        event=event)
    a = services.save_draft(ann(event, levels["info"]), actor=control, request=tf(control))
    services.submit(a, actor=control, request=tf(control))
    assert a.status == "pending"
    settings_store.save("announcements", "event", str(event.pk), {"approval_required": False}, user=admin,
                        event=event)
    levels["info"].requires_approval = True
    levels["info"].save()
    b = services.save_draft(ann(event, levels["info"]), actor=control, request=tf(control))
    assert services.needs_approval(b, control, tf(control))


def test_emergency_needs_permission_and_skips_approval(event, levels, helpdesk, control, client, run):
    a = services.save_draft(ann(event, levels["emergency"], title="Storm"), actor=helpdesk)
    with pytest.raises(PermissionDenied):
        services.submit(a, actor=helpdesk)
    # sensitive permission: without a request (no session) the control room has it only with two factors
    login_2fa(client, control)
    request = client.get("/").wsgi_request
    run(services.submit, a, actor=control, request=request)
    assert a.status == "live" and a.decision_note.startswith("emergency")
    with pytest.raises(PermissionDenied):
        services.cancel(a, actor=User.objects.create_user(email="x@example.org", password="pw-x-123456789"))
    services.cancel(a, actor=helpdesk)  # the author may withdraw it
    assert a.status == "cancelled"
    with pytest.raises(ValidationError):
        services.cancel(a, actor=helpdesk)


def test_drafting_needs_a_permission(event, levels, member):
    with pytest.raises(PermissionDenied):
        services.save_draft(ann(event, levels["info"]), actor=member)


def test_scoped_sender_may_only_target_own_zone(event, venue, levels, role):
    north, south = venue.zones.get(name="North"), venue.zones.get(name="South")
    u = User.objects.create_user(email="north@example.org", password="pw-north-12345")
    event_services.assign_role(event, u, role("control-room"), scope_kind="zone", scope_id=str(north.pk),
                               scope_label="North")
    mine = services.save_draft(ann(event, levels["info"], all_screens=False), actor=u, request=tf(u),
                               m2m={"zones": [north]})
    assert services.may_target(u, mine, "announcements.publish", tf(u))
    services.submit(mine, actor=u, request=tf(u))
    assert mine.status == "live"
    theirs = services.save_draft(ann(event, levels["info"], all_screens=False), actor=u, request=tf(u),
                                 m2m={"zones": [south]})
    assert not services.may_target(u, theirs, "announcements.publish", tf(u))
    with pytest.raises(PermissionDenied):
        services.submit(theirs, actor=u, request=tf(u))
    everywhere = services.save_draft(ann(event, levels["info"]), actor=u, request=tf(u))
    with pytest.raises(PermissionDenied):
        services.submit(everywhere, actor=u, request=tf(u))
    assert mine.target_label() == "North"
    assert Announcement(all_screens=True).target_label() == "Everywhere"


# ------------------------------------------------------------------ timing
def test_duration_occurrences_and_windows(event, levels):
    t0 = dt.datetime(2026, 7, 1, 12, tzinfo=dt.UTC)
    a = ann(event, levels["info"], starts_at=t0)
    assert services.duration(a) == dt.timedelta(seconds=60)
    a.ends_at = t0 + dt.timedelta(hours=1)
    assert services.screen_windows(a, t0, t0 + dt.timedelta(days=1)) == [[t0, t0 + dt.timedelta(hours=1)]]
    daily = ann(event, levels["info"], starts_at=t0, ends_at=t0 + dt.timedelta(minutes=30), recurrence="daily",
                recurrence_until=dt.date(2026, 7, 3))
    occ = services.occurrences(daily, t0, t0 + dt.timedelta(days=10))
    assert [o.day for o in occ] == [1, 2, 3]
    assert services.occurrences(daily, t0 + dt.timedelta(hours=2), t0 + dt.timedelta(days=1, hours=1)) == [
        t0 + dt.timedelta(days=1)]
    # urgent repeats every 10 minutes for 60 seconds until cancelled
    rep = ann(event, levels["urgent"], starts_at=t0)
    assert services.duration(rep) is None
    wins = services.screen_windows(rep, t0, t0 + dt.timedelta(minutes=25))
    assert wins == [[t0 + dt.timedelta(minutes=m), t0 + dt.timedelta(minutes=m, seconds=60)] for m in (0, 10, 20)]


def test_publish_due_sends_occurrences_and_ends(admin, event, levels, run):
    t0 = timezone.now() - dt.timedelta(days=1, minutes=1)
    a = services.save_draft(ann(event, levels["info"], starts_at=t0, ends_at=t0 + dt.timedelta(minutes=5),
                                recurrence="daily", recurrence_until=timezone.now().date()), actor=admin)
    run(services.submit, a, actor=admin)  # starts in the past: first occurrence goes out now
    a.refresh_from_db()
    assert a.status == "live"
    assert run(services.publish_due) == 1  # today's occurrence
    a.refresh_from_db()
    assert a.last_occurrence == t0 + dt.timedelta(days=1)
    assert run(services.publish_due) == 0
    later = ann(event, levels["info"], starts_at=timezone.now() + dt.timedelta(hours=1))
    services.save_draft(later, actor=admin)
    services.submit(later, actor=admin)
    assert later.status == "scheduled"
    once = services.save_draft(ann(event, levels["info"], starts_at=timezone.now() - dt.timedelta(minutes=5)),
                               actor=admin)
    run(services.submit, once, actor=admin)
    from apps.announcements.tasks import publish_due

    publish_due()
    once.refresh_from_db()
    assert once.status == "ended"  # 60 seconds of info level are over


# ------------------------------------------------------------------ screens
def test_program_source_overlays_and_takeover(admin, event, levels, paired, client):
    screen, token = paired
    info = services.save_draft(ann(event, levels["info"], title="Bar open", short="Bar is open"), actor=admin)
    services.submit(info, actor=admin)
    emergency = services.save_draft(ann(event, levels["emergency"], title="Storm", body="Leave the field"),
                                    actor=admin)
    services._approve(emergency, actor=admin)
    staff_only = services.save_draft(ann(event, levels["important"], channels=["staff"]), actor=admin)
    services.submit(staff_only, actor=admin)
    program = client.get("/player/api/playlists/program/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["program"]
    assert [o["text"] for o in program["overlays"]] == ["Bar is open"]
    assert program["overlays"][0]["style"] == "ticker"
    entry = next(e for e in program["entries"] if e["source"] == "announcement")
    assert entry["priority"] == 500 and entry["content"] == {"message": f"announcement:{emergency.pk}"}
    layout = program["messages"][f"announcement:{emergency.pk}"]
    assert layout["background"]["color"] == levels["emergency"].colour
    assert [e["props"]["text"] for e in layout["elements"] if e["id"] in ("title", "text")] == ["Storm",
                                                                                               "Leave the field"]
    now = playlists.now_playing(screen)
    assert now["source"] == "announcement"
    # module off: nothing from announcements
    modules.set_event(event, "announcements", False, user=admin)
    program = playlists.screen_program(screen)
    assert program["overlays"] == [] and all(e["source"] != "announcement" for e in program["entries"])


def test_targeting_screens(admin, event, levels, paired):
    screen, _token = paired
    group = ScreenGroup(event=event, name="Stage")
    screen_services.save_group(group, actor=admin)
    target = playlists.Target(screen=screen)
    a = services.save_draft(ann(event, levels["info"], all_screens=False), actor=admin, m2m={"screen_groups": [group]})
    assert not services.applies_to(a, target)
    screen.manual_groups.add(group)
    assert services.applies_to(a, playlists.Target(screen=screen))
    b = services.save_draft(ann(event, levels["info"], all_screens=False), actor=admin, m2m={"screens": [screen]})
    assert services.applies_to(b, target)


def test_takeover_with_template_layout(admin, event, levels):
    lay = content.create_layout(event, name="Alert", key="alert", actor=admin)
    data = dict(lay.data)
    data["elements"] = [{"id": "t", "type": "text", "name": "T", "frame": {"x": 0, "y": 0, "w": 100, "h": 20},
                         "style": {}, "props": {"text": "{{ announcement.title }} – {{announcement.text}}"}}]
    content.save_layout(lay, data, actor=admin)
    content.publish_layout(lay, actor=admin)
    tpl = services.save_template(Template(event=event, name="Alert", title="Alert", layout=lay,
                                          level=levels["emergency"]), actor=admin)
    a = ann(event, levels["emergency"], title='Say "hi"', body="Now", template=tpl)
    out = services.takeover_layout(a)
    assert out["elements"][0]["props"]["text"] == 'Say "hi" – Now'


def test_text_colour_contrast():
    assert services.text_on("#b91c1c") == "#ffffff"
    assert services.text_on("#d97706") == "#000000"
    assert services.text_on("#fde047") == "#000000"
    assert services.text_on("nope") == "#ffffff"


# ------------------------------------------------------------------ delivery details
def test_delivery_channels(admin, event, levels, run):
    a = services.save_draft(ann(event, levels["urgent"], channels=["feed", "webhook"]), actor=admin)
    run(services.submit, a, actor=admin)
    report = {d.channel: d for d in a.deliveries.all()}
    assert report["feed"].status == "skipped"
    assert report["webhook"].status == "sent"
    d = Delivery.objects.create(announcement=a, channel="nowhere", occurrence=a.starts_at)
    services.deliver(OutboxJob(payload={"delivery": str(d.pk)}))
    d.refresh_from_db()
    assert d.status == "skipped" and d.attempts == 1
    assert "screens" not in services.available_channels(event) or modules.is_enabled("screens", event)
    modules.set_event(event, "screens", False, user=admin)
    assert "screens" not in services.available_channels(event)


def test_failed_delivery_is_recorded(admin, event, levels, monkeypatch):
    a = services.save_draft(ann(event, levels["info"], channels=["staff"]), actor=admin)
    d = Delivery.objects.create(announcement=a, channel="staff", occurrence=a.starts_at)
    monkeypatch.setattr(services, "staff_recipients", lambda event: 1 / 0)
    from apps.core.registry import registry

    spec = registry.notification_channels["staff"]
    monkeypatch.setitem(registry.notification_channels, "staff",
                        type(spec)(key="staff", name="Staff", send=services.send_staff, module=spec.module))
    with pytest.raises(ZeroDivisionError):
        services.deliver(OutboxJob(payload={"delivery": str(d.pk)}))
    d.refresh_from_db()
    assert d.status == "failed" and "ZeroDivisionError" in d.detail


# ------------------------------------------------------------------ pages
def test_compose_send_and_detail_pages(client, admin, event, levels, run):
    login_2fa(client, admin)
    tpl = Template.objects.get(event=event, name="Doors open soon")
    page = client.get(f"/e/demo/announcements/new/?template={tpl.pk}")
    assert page.status_code == 200 and b"var_minutes" in page.content and b"var_place" in page.content
    assert client.get("/e/demo/announcements/new/?template=nope").status_code == 200
    assert client.get("/e/demo/announcements/new/?level=urgent").status_code == 200
    with_vars = {"template": tpl.pk, "level": levels["important"].pk, "title": tpl.title, "body": tpl.body,
                 "short": tpl.short, "channels": ["screens", "staff"], "all_screens": "on", "var_minutes": "15",
                 "var_place": "The main hall", "action": "send"}
    response = run(client.post, "/e/demo/announcements/new/", with_vars)
    a = Announcement.objects.get()
    assert response.status_code == 302 and a.title == "Doors open in 15 minutes" and a.status == "live"
    assert a.variables == {"minutes": "15", "place": "The main hall"}
    detail = client.get(f"/e/demo/announcements/{a.pk}/")
    assert b"Delivery report" in detail.content and b"Staff notifications" in detail.content
    # missing variable -> form error
    bad = client.post("/e/demo/announcements/new/", {**with_vars, "var_minutes": ""})
    assert bad.status_code == 200 and bad.context["form"].errors
    # nowhere -> form error
    nowhere = client.post("/e/demo/announcements/new/", {**with_vars, "all_screens": ""})
    assert "Choose where" in str(nowhere.context["form"].non_field_errors())
    # cancel
    client.post(f"/e/demo/announcements/{a.pk}/cancel/")
    a.refresh_from_db()
    assert a.status == "cancelled"
    assert client.get(f"/e/demo/announcements/{a.pk}/edit/").status_code == 302
    for url in ["/e/demo/announcements/", "/e/demo/announcements/levels/", "/e/demo/announcements/templates/",
                "/e/demo/announcements/templates/new/", f"/e/demo/announcements/levels/{levels['info'].pk}/"]:
        assert client.get(url).status_code == 200, url


def test_draft_and_approval_pages(client, event, levels, helpdesk, control):
    login_2fa(client, helpdesk)
    data = {"level": levels["info"].pk, "title": "Lost keys", "body": "", "short": "", "channels": ["staff"],
            "all_screens": "on", "action": "draft"}
    client.post("/e/demo/announcements/new/", data)
    a = Announcement.objects.get()
    assert a.status == "draft" and a.channels == ["staff"]
    client.post(f"/e/demo/announcements/{a.pk}/edit/", {**data, "title": "Lost keys (blue)"})
    a.refresh_from_db()
    assert a.title == "Lost keys (blue)"
    client.post(f"/e/demo/announcements/{a.pk}/submit/")
    a.refresh_from_db()
    assert a.status == "pending"
    # the emergency level is not offered to the helpdesk
    form = client.get("/e/demo/announcements/new/").context["form"]
    assert levels["emergency"] not in form.fields["level"].queryset
    assert client.get("/e/demo/announcements/levels/").status_code == 200
    assert client.get(f"/e/demo/announcements/levels/{levels['info'].pk}/").status_code == 403
    login_2fa(client, control)
    page = client.get(f"/e/demo/announcements/{a.pk}/")
    assert b"Approve and send" in page.content
    client.post(f"/e/demo/announcements/{a.pk}/reject/", {"note": "Which desk?"})
    a.refresh_from_db()
    assert a.status == "rejected" and a.decision_note == "Which desk?"
    client.post(f"/e/demo/announcements/{a.pk}/approve/")  # not pending any more: an error message, no change
    a.refresh_from_db()
    assert a.status == "rejected"
    login_2fa(client, helpdesk)
    client.post(f"/e/demo/announcements/{a.pk}/delete/")
    assert not Announcement.objects.exists()


def test_levels_and_templates_pages(admin_client, event, levels):
    lv = levels["info"]
    r = admin_client.post(f"/e/demo/announcements/levels/{lv.pk}/", {
        "name": "Info", "rank": 11, "colour": "#16A34A", "display": "banner", "sound": "chime",
        "min_display_seconds": 30, "repeat_every_minutes": 0, "default_channels": ["screens"]})
    assert r.status_code == 302
    lv.refresh_from_db()
    assert (lv.colour, lv.display, lv.default_channels) == ("#16a34a", "banner", ["screens"])
    bad = admin_client.post(f"/e/demo/announcements/levels/{lv.pk}/", {"name": "Info", "rank": 1, "colour": "red",
                                                                         "display": "banner", "sound": "none",
                                                                         "min_display_seconds": 30,
                                                                         "repeat_every_minutes": 0})
    assert bad.status_code == 200
    admin_client.post("/e/demo/announcements/templates/new/", {"name": "Bar closes", "level": lv.pk,
                                                                "title": "Bar closes in {{minutes}} min"})
    tpl = Template.objects.get(name="Bar closes")
    assert AuditLog.objects.filter(action="announcement_template.created").exists()
    admin_client.post(f"/e/demo/announcements/templates/{tpl.pk}/", {"name": "Bar closes soon", "level": lv.pk,
                                                                      "title": "Bar closes"})
    tpl.refresh_from_db()
    assert tpl.name == "Bar closes soon"
    assert admin_client.get(f"/e/demo/announcements/templates/{tpl.pk}/").status_code == 200
    admin_client.post(f"/e/demo/announcements/templates/{tpl.pk}/", {"action": "delete"})
    assert not Template.objects.filter(pk=tpl.pk).exists()


def test_module_off_hides_pages(admin_client, admin, event):
    modules.set_event(event, "announcements", False, user=admin)
    assert admin_client.get("/e/demo/announcements/").status_code == 404
    assert b"/e/demo/announcements/" not in admin_client.get("/e/demo/").content


def test_public_feed(client, admin, event, levels, run):
    assert client.get("/public/demo/announcements/").status_code == 404
    settings_store.save("announcements", "event", str(event.pk), {"public_feed": True, "feed_title": "Camp news"},
                        user=admin, event=event)
    a = services.save_draft(ann(event, levels["info"], title="Bar open", body="Until 2 am",
                                channels=["feed", "screens"]), actor=admin)
    run(services.submit, a, actor=admin)
    assert a.deliveries.get(channel="feed").status == "sent"
    hidden = services.save_draft(ann(event, levels["info"], title="Staff only", channels=["staff"]), actor=admin)
    run(services.submit, hidden, actor=admin)
    page = client.get("/public/demo/announcements/")
    assert page.status_code == 200 and b"Camp news" in page.content and b"Bar open" in page.content
    assert b"Staff only" not in page.content
    feed = client.get("/public/demo/announcements/feed.json").json()
    assert feed["title"] == "Camp news" and [i["title"] for i in feed["items"]] == ["Bar open"]
    rss = client.get("/public/demo/announcements/rss.xml")
    assert rss["Content-Type"].startswith("application/rss+xml") and b"Info: Bar open" in rss.content
    assert audit_url(client, "/public/demo/announcements/") == []


def test_pages_are_accessible(admin_client, event, levels, admin):
    a = services.save_draft(ann(event, levels["info"]), actor=admin)
    for url in ["/e/demo/announcements/", "/e/demo/announcements/new/", f"/e/demo/announcements/{a.pk}/",
                "/e/demo/announcements/levels/", "/e/demo/announcements/templates/",
                f"/e/demo/announcements/levels/{levels['urgent'].pk}/", "/e/demo/announcements/templates/new/"]:
        assert audit_url(admin_client, url) == [], url


# ------------------------------------------------------------------ API
def test_api(admin, event, levels, helpdesk, control, run):
    api = APIClient()
    api.force_authenticate(helpdesk)
    base = "/api/v1/events/demo/announcements/"
    assert len(api.get("/api/v1/events/demo/announcement-levels/").json()["results"]) == 4
    tpls = api.get("/api/v1/events/demo/announcement-templates/").json()["results"]
    lost = next(t for t in tpls if t["name"] == "Lost child")
    assert lost["variables"] == ["description", "desk"] and lost["level"] == "urgent"
    r = api.post(base, {"template": lost["id"], "variables": {"description": "red cap", "desk": "info"},
                        "level": "urgent", "send": True}, format="json")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["status"] == "pending" and body["title"] == "Lost child" and "red cap" in body["body"]
    assert body["channels"] == levels["urgent"].default_channels
    assert api.post(f"{base}{body['id']}/approve/").status_code == 403  # four eyes
    api.force_authenticate(None)
    login_2fa(api, control)
    r = run(api.post, f"{base}{body['id']}/approve/", {"note": "go"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "live"
    assert {d["channel"] for d in r.json()["deliveries"]} == set(levels["urgent"].default_channels)
    assert api.post(f"{base}{body['id']}/approve/").status_code == 400
    assert api.post(f"{base}{body['id']}/cancel/").json()["status"] == "cancelled"
    # draft, edit, submit
    r = api.post(base, {"level": "info", "title": "Hi", "channels": ["staff"], "zones": [
        str(event.venues.first().zones.first().pk)]}, format="json")
    assert r.status_code == 201 and r.json()["status"] == "draft"
    a = Announcement.objects.get(pk=r.json()["id"])
    assert not a.all_screens and a.zones.count() == 1
    r = api.patch(f"{base}{a.pk}/", {"title": "Hello"}, format="json")
    assert r.json()["title"] == "Hello"
    assert api.post(f"{base}{a.pk}/submit/").json()["status"] == "live"
    assert api.post(f"{base}{a.pk}/reject/").status_code == 400
    assert api.post(base, {"level": "info", "title": "", "channels": ["staff"]}, format="json").status_code == 400
    assert api.post(base, {"level": "info", "title": "x", "variables": [1]}, format="json").status_code == 400
    assert api.post(base, {"level": "info", "title": "x", "channels": "staff"}, format="json").status_code == 400
    assert api.get(f"{base}?status=live").json()["count"] == 1
    # a viewer may read but not write; the module switch hides everything
    viewer = User.objects.create_user(email="v@example.org", password="pw-v-123456789")
    event_services.assign_role(event, viewer, event.roles.get(key="viewer"))
    api.logout()
    api.force_authenticate(viewer)
    assert api.get(base).status_code == 200
    assert api.post(base, {"level": "info", "title": "x", "channels": ["staff"]}, format="json").status_code == 403
    modules.set_event(event, "announcements", False, user=admin)
    assert api.get(base).status_code == 404


def test_api_token_scope(admin, event, levels):
    tok, raw = ServiceToken.issue(name="ci", owner=admin, scopes=["announcements:read"], event=event)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert api.get("/api/v1/events/demo/announcements/").status_code == 200
    assert api.post("/api/v1/events/demo/announcements/", {"level": "info", "title": "x"},
                    format="json").status_code == 403
