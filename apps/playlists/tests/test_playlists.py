# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken, User
from apps.content import services as content
from apps.core import modules
from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.events import services as event_services
from apps.playlists import services
from apps.playlists.models import Override, Playlist, PlaylistItem, ScheduleRule
from apps.screens import channel
from apps.screens import services as screen_services
from apps.screens.models import ScreenGroup
from conftest import login_2fa

BERLIN = ZoneInfo("Europe/Berlin")


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def layouts(admin, event):
    out = []
    for n, name in enumerate(["Welcome", "Concert", "Draft"]):
        lay = content.create_layout(event, name=name, key=name.lower(), actor=admin)
        if n < 2:
            data = dict(lay.data, duration=6 + n)
            content.save_layout(lay, data, actor=admin)
            content.publish_layout(lay, actor=admin)
        out.append(lay)
    return out


@pytest.fixture
def paired(client, admin, event):
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    screen = screen_services.pair(event, data["code"], actor=admin, name="Foyer", tags=["stage"])
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    return screen, token


@pytest.fixture
def group(admin, event, paired):
    g = ScreenGroup(event=event, name="Stage")
    screen_services.save_group(g, actor=admin)
    paired[0].manual_groups.add(g)
    return g


def _playlist(admin, event, name, layouts, **kw):
    pl = services.save_playlist(Playlist(event=event, name=name, **kw), actor=admin)
    for lay in layouts:
        services.save_item(PlaylistItem(playlist=pl, layout=lay), actor=admin)
    return pl


def ms(d):
    return int(d.timestamp() * 1000)


def test_schedule_windows_recurring_overnight_and_dst():
    rule = ScheduleRule(weekdays=[4, 5], start_time=dt.time(22), end_time=dt.time(2),
                        start_date=dt.date(2026, 10, 1), end_date=dt.date(2026, 10, 31))
    start = dt.datetime(2026, 10, 19, tzinfo=BERLIN)
    wins = services.schedule_windows(rule, start, start + dt.timedelta(days=14), BERLIN)
    as_local = [(dt.datetime.fromtimestamp(a / 1000, BERLIN), dt.datetime.fromtimestamp(b / 1000, BERLIN))
                for a, b in wins]
    assert [(a.strftime("%a %d %H:%M"), b.strftime("%a %d %H:%M")) for a, b in as_local] == [
        ("Fri 23 22:00", "Sat 24 02:00"), ("Sat 24 22:00", "Sun 25 02:00"),
        ("Fri 30 22:00", "Sat 31 02:00"), ("Sat 31 22:00", "Sun 01 02:00")]
    assert wins[1][1] - wins[1][0] == 4 * 3600 * 1000  # the clocks go back at 03:00, after this slot
    # the day of the DST change has 25 hours
    dst = ScheduleRule(start_date=dt.date(2026, 10, 25), end_date=dt.date(2026, 10, 25))
    [(a, b)] = services.schedule_windows(dst, start, start + dt.timedelta(days=14), BERLIN)
    assert b - a == 25 * 3600 * 1000
    # all-day rule: consecutive days merge into one window, clipped to the range
    every = ScheduleRule()
    assert services.schedule_windows(every, start, start + dt.timedelta(days=2), BERLIN) == [
        [ms(start), ms(start + dt.timedelta(days=2))]]
    # a day range without times
    day = ScheduleRule(start_date=dt.date(2026, 10, 20), end_date=dt.date(2026, 10, 20))
    assert services.schedule_windows(day, start, start + dt.timedelta(days=7), BERLIN) == [
        [ms(dt.datetime(2026, 10, 20, tzinfo=BERLIN)), ms(dt.datetime(2026, 10, 21, tzinfo=BERLIN))]]


@pytest.mark.django_db
def test_program_priorities_and_player_endpoint(client, admin, event, layouts, paired, group,
                                                django_capture_on_commit_callbacks):
    screen, token = paired
    welcome, concert, draft = layouts
    # without a playlist: the default layout (the first one created) is the default entry
    prog = client.get("/player/api/playlists/program/", HTTP_AUTHORIZATION=f"Screen {token}").json()["program"]
    assert [e["id"] for e in prog["entries"]] == ["default"]
    assert prog["entries"][0]["content"] == {"layout": str(welcome.pk)}
    assert set(prog["layouts"]) == {str(welcome.pk), str(concert.pk)}  # the draft is not published
    assert prog["layouts"][str(concert.pk)] == 7000

    seq = channel.last_seq(screen.pk)
    loop = _playlist(admin, event, "Loop", [welcome, concert, draft], is_default=True)
    assert channel.last_seq(screen.pk) > seq  # screens were told to fetch their program
    show = _playlist(admin, event, "Show", [concert])
    now = timezone.now()
    services.save_rule(ScheduleRule(event=event, name="Stage evening", playlist=show), actor=admin,
                       m2m={"groups": [group]})
    services.save_rule(ScheduleRule(event=event, name="Elsewhere", layout=welcome, priority=50), actor=admin,
                       m2m={"screens": []})
    services.save_rule(ScheduleRule(event=event, name="Off", layout=welcome, enabled=False, all_screens=True),
                       actor=admin)
    ov = services.push_override(Override(event=event, title="Doors open", message="Welcome!", level="urgent",
                                         all_screens=True, starts_at=now, expires_at=now + dt.timedelta(hours=1)),
                                actor=admin)
    prog = services.screen_program(screen)
    assert [(e["source"], e["priority"]) for e in prog["entries"]] == [
        ("override", 200), ("schedule", 100), ("default", 0)]
    assert prog["playlists"][str(loop.pk)]["items"][0]["duration"] is None
    assert str(ov.pk) in prog["messages"]
    ctx = services.Target(screen=screen).context(event)
    assert ctx["screen"]["groups"] == ["Stage"]
    on = services.now_playing(screen)
    assert on["source"] == "override" and on["message"] == str(ov.pk)
    services.cancel_override(ov, actor=admin)
    services.cancel_override(ov, actor=admin)  # idempotent
    on = services.now_playing(screen)
    assert on["source"] == "schedule" and on["layout"] == str(concert.pk)
    assert services.now_playing(screen, at=now)["name"] == "Stage evening"
    rule = ScheduleRule.objects.get(name="Stage evening")
    rule.enabled = False
    services.save_rule(rule, actor=admin)
    on = services.now_playing(screen)
    assert on["source"] == "default" and on["count"] == 2  # the unpublished draft is skipped

    # modules switched off: schedules/overrides vanish from the program; playlists off -> no program
    modules.set_event(event, "overrides", False, user=admin)
    assert all(e["source"] != "override" for e in services.screen_program(screen)["entries"])
    modules.set_event(event, "playlists", False, user=admin)
    resp = client.get("/player/api/playlists/program/", HTTP_AUTHORIZATION=f"Screen {token}")
    assert resp.json() == {"program": None}
    assert client.get("/player/api/playlists/program/").status_code == 401
    assert client.get("/e/demo/playlists/").status_code in (302, 404)


@pytest.mark.django_db
def test_nested_cycle_and_validation(admin, event, layouts):
    welcome = layouts[0]
    a = _playlist(admin, event, "A", [welcome])
    b = _playlist(admin, event, "B", [welcome])
    services.save_item(PlaylistItem(playlist=a, child=b), actor=admin)
    with pytest.raises(ValidationError):
        services.save_item(PlaylistItem(playlist=b, child=a), actor=admin)
    with pytest.raises(ValidationError):
        services.save_item(PlaylistItem(playlist=a, child=a), actor=admin)
    with pytest.raises(ValidationError):
        services.save_item(PlaylistItem(playlist=a), actor=admin)
    with pytest.raises(ValidationError):
        services.save_item(PlaylistItem(playlist=a, layout=welcome, child=b), actor=admin)
    other = event_services.create_event(name="Other", slug="other", user=admin)
    foreign = content.create_layout(other, name="X", key="x", actor=admin)
    with pytest.raises(ValidationError):
        services.save_item(PlaylistItem(playlist=a, layout=foreign), actor=admin)
    prog = services.build_program(event, services.Target(), now=timezone.now())
    assert prog["entries"] == [] or prog["entries"][0]["source"] == "default"
    payload = services._collect_playlists(event, {str(a.pk)})
    assert set(payload) == {str(a.pk), str(b.pk)}
    # items move and get removed
    items = list(a.items.all())
    services.move_item(items[1], -1, actor=admin)
    assert [i.pk for i in a.items.all()] == [items[1].pk, items[0].pk]
    services.move_item(items[1], -5, actor=admin)  # already first: no-op
    services.delete_item(items[1], actor=admin)
    assert a.items.count() == 1
    rule = services.save_rule(ScheduleRule(event=event, name="R", playlist=a, all_screens=True), actor=admin)
    with pytest.raises(ValidationError):
        services.delete_playlist(a, actor=admin)
    services.delete_rule(rule, actor=admin)
    services.delete_playlist(a, actor=admin)
    with pytest.raises(ValidationError):
        services.save_rule(ScheduleRule(event=event, name="Both", playlist=b, layout=welcome), actor=admin)
    with pytest.raises(ValidationError):
        services.push_override(Override(event=event, title="Empty", all_screens=True), actor=admin)
    with pytest.raises(ValidationError):
        services.push_override(Override(event=event, title="Nobody", message="x"), actor=admin)
    assert not Override.objects.filter(title="Nobody").exists()
    now = timezone.now()
    with pytest.raises(ValidationError):
        services.push_override(Override(event=event, title="Back", message="x", all_screens=True, starts_at=now,
                                        expires_at=now - dt.timedelta(minutes=1)), actor=admin)


@pytest.mark.django_db
def test_override_states_and_message_layout(admin, event):
    now = timezone.now()
    ov = Override(event=event, title="Storm", message="Stay inside", level="emergency", all_screens=True,
                  starts_at=now + dt.timedelta(minutes=5))
    assert ov.state(now) == "scheduled" and ov.priority == 400 and ov.is_message
    ov.expires_at = now - dt.timedelta(seconds=1)
    assert ov.state(now) == "expired"
    ov.cancelled_at = now
    assert ov.state(now) == "cancelled"
    data = services.message_layout(ov, 1080, 1920)
    assert data["height"] == 1920 and data["background"]["color"] == "token:danger"
    from apps.content import layout_format

    assert layout_format.validate(data) == []


@pytest.mark.django_db
def test_pages(client, admin, event, layouts, paired, group, django_capture_on_commit_callbacks):
    login_2fa(client, admin)
    screen, _token = paired
    welcome, concert, _draft = layouts
    r = client.post("/e/demo/playlists/lists/", {"new-name": "Loop", "new-mode": "ordered",
                                                  "new-default_duration": 10, "new-is_default": "on"})
    pl = Playlist.objects.get(name="Loop")
    assert r.status_code == 302 and pl.is_default
    url = f"/e/demo/playlists/lists/{pl.pk}/"
    for lay in (welcome, concert):
        r = client.post(url, {"action": "add", "add-layout": lay.pk, "add-weight": 1, "add-enabled": "on",
                              "add-tags": "stage, foyer"})
        assert r.status_code == 302
    r = client.post(url, {"action": "add", "add-weight": 1})
    assert r.status_code == 200 and "Choose either" in r.content.decode()
    items = list(pl.items.all())
    assert items[0].tags == ["stage", "foyer"]
    client.post(url, {"action": "down", "item": items[0].pk})
    client.post(url, {"action": "toggle", "item": items[0].pk})
    assert not PlaylistItem.objects.get(pk=items[0].pk).enabled
    client.post(url, {"meta-name": "Loop", "meta-mode": "shuffle", "meta-default_duration": 8,
                      "meta-is_default": "on"})
    assert Playlist.objects.get(pk=pl.pk).mode == "shuffle"
    page = client.get(url).content.decode()
    assert "Welcome" in page and "Concert" in page

    r = client.post("/e/demo/playlists/schedules/new/", {
        "name": "Evening", "enabled": "on", "layout": concert.pk, "groups": [group.pk], "weekdays": [0, 1, 2],
        "start_time": "18:00", "end_time": "20:00", "priority": 5})
    assert r.status_code == 302, r.content.decode()[:2000]
    rule = ScheduleRule.objects.get(name="Evening")
    assert rule.weekdays == [0, 1, 2] and list(rule.groups.all()) == [group]
    r = client.post("/e/demo/playlists/schedules/new/", {"name": "Nothing", "priority": 0})
    assert r.status_code == 200 and "Choose either a playlist or a layout" in r.content.decode()
    cal = client.get(f"/e/demo/playlists/calendar/?group={group.pk}&week=2026-07-01").content.decode()
    assert "Evening" in cal and "cal-block" in cal

    r = client.post("/e/demo/playlists/overrides/", {"title": "Doors", "level": "override", "message": "Open!",
                                                     "all_screens": "on", "duration": "15"})
    assert r.status_code == 302
    ov = Override.objects.get(title="Doors")
    assert ov.expires_at - ov.starts_at == dt.timedelta(minutes=15)
    assert AuditLog.objects.filter(action="override.pushed").exists()
    r = client.post("/e/demo/playlists/overrides/", {"title": "Bad", "level": "override", "all_screens": "on",
                                                     "duration": "custom"})
    assert r.status_code == 200 and not Override.objects.filter(title="Bad").exists()
    index = client.get("/e/demo/playlists/").content.decode()
    assert "Doors" in index and "Foyer" in index
    prev = client.get(f"/e/demo/playlists/preview/?screen={screen.pk}").content.decode()
    assert "preview-config" in prev and "wins" in prev
    later = (timezone.now() + dt.timedelta(days=1)).astimezone(BERLIN).strftime("%Y-%m-%dT%H:%M")
    assert client.get(f"/e/demo/playlists/preview/?screen={screen.pk}&at={later}").status_code == 200
    r = client.post(f"/e/demo/playlists/overrides/{ov.pk}/cancel/", {"next": "/e/demo/playlists/"})
    assert r.status_code == 302 and r["Location"] == "/e/demo/playlists/"
    assert Override.objects.get(pk=ov.pk).cancelled_at
    r = client.post(f"/e/demo/playlists/overrides/{ov.pk}/cancel/", {"next": "https://evil.example/"})
    assert r["Location"] == "/e/demo/playlists/overrides/"
    for page_url in ["/e/demo/playlists/", url, "/e/demo/playlists/schedules/",
                     f"/e/demo/playlists/schedules/{rule.pk}/", "/e/demo/playlists/calendar/",
                     "/e/demo/playlists/overrides/",
                     f"/e/demo/playlists/preview/?screen={screen.pk}"]:
        assert audit_url(client, page_url) == [], page_url
    client.post(f"/e/demo/playlists/schedules/{rule.pk}/", {"action": "delete"})
    assert not ScheduleRule.objects.filter(pk=rule.pk).exists()
    client.post(url, {"action": "remove", "item": items[1].pk})
    client.post(url, {"action": "delete"})
    assert not Playlist.objects.filter(pk=pl.pk).exists()


@pytest.mark.django_db
def test_permissions_and_scopes(client, admin, event, role, layouts, paired, group):
    viewer = User.objects.create_user(email="v@example.org", password="pw-viewer-1234")
    event_services.assign_role(event, viewer, role("viewer"))
    login_2fa(client, viewer)
    assert client.get("/e/demo/playlists/").status_code == 200
    assert client.post("/e/demo/playlists/lists/", {"new-name": "X"}).status_code == 403
    assert client.get("/e/demo/playlists/schedules/new/").status_code == 403
    page = client.get("/e/demo/playlists/overrides/").content.decode()
    assert "Push an override" not in page
    # a control-room member limited to the Stage group may push there, but not to all screens or emergencies
    op = User.objects.create_user(email="op@example.org", password="pw-op-1234567")
    cr = role("control-room")
    event_services.assign_role(event, op, cr, scope_kind="screen_group", scope_id=str(group.pk), actor=admin)
    login_2fa(client, op)
    r = client.post("/e/demo/playlists/overrides/", {"title": "All", "level": "override", "message": "x",
                                                     "all_screens": "on", "duration": "5"})
    assert r.status_code == 200 and not Override.objects.filter(title="All").exists()
    r = client.post("/e/demo/playlists/overrides/", {"title": "Stage", "level": "override", "message": "x",
                                                     "groups": [group.pk], "duration": "5"})
    assert r.status_code == 302 and Override.objects.filter(title="Stage").exists()
    page = client.get("/e/demo/playlists/overrides/").content.decode()
    assert 'value="emergency"' in page  # control room has playlists.* (emergency is sensitive: 2FA session)
    # a custom role without the emergency permission does not even see the level
    limited = event.roles.create(key="screens-op", name="Screens operator",
                                 permissions=["playlists.view", "playlists.override"])
    op2 = User.objects.create_user(email="op2@example.org", password="pw-op2-123456")
    event_services.assign_role(event, op2, limited, actor=admin)
    login_2fa(client, op2)
    assert 'value="emergency"' not in client.get("/e/demo/playlists/overrides/").content.decode()
    r = client.post("/e/demo/playlists/overrides/", {"title": "E", "level": "emergency", "message": "x",
                                                     "all_screens": "on", "duration": "5"})
    assert r.status_code == 200 and not Override.objects.filter(title="E").exists()


@pytest.mark.django_db
def test_api(admin, event, layouts, paired, group):
    welcome, concert, _ = layouts
    _tok, raw = ServiceToken.issue(name="t", owner=admin, scopes=["playlists:write"])
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    base = "/api/v1/events/demo"
    r = api.post(f"{base}/playlists/", {"name": "Loop", "is_default": True, "items": [
        {"layout": str(welcome.pk), "duration": 5}, {"layout": str(concert.pk), "tags": ["stage"]}]}, format="json")
    assert r.status_code == 201, r.content
    pid = r.json()["id"]
    assert [i["duration"] for i in r.json()["items"]] == [5, None]
    r = api.patch(f"{base}/playlists/{pid}/", {"items": [{"layout": str(concert.pk)}]}, format="json")
    assert r.status_code == 200 and len(r.json()["items"]) == 1
    r = api.patch(f"{base}/playlists/{pid}/", {"items": [{"child": pid}]}, format="json")
    assert r.status_code == 400
    r = api.post(f"{base}/schedules/", {"name": "Eve", "playlist": pid, "groups": [str(group.pk)],
                                        "weekdays": [5, 5, 6], "start_time": "18:00", "end_time": "23:00"},
                 format="json")
    assert r.status_code == 201, r.content
    assert r.json()["weekdays"] == [5, 6]
    assert api.post(f"{base}/schedules/", {"name": "Bad", "playlist": pid, "all_screens": True,
                                           "weekdays": [9]}, format="json").status_code == 400
    assert api.post(f"{base}/schedules/", {"name": "None", "all_screens": True}, format="json").status_code == 400
    r = api.post(f"{base}/overrides/", {"title": "Doors", "message": "Open", "all_screens": True}, format="json")
    assert r.status_code == 201 and r.json()["state"] == "active"
    oid = r.json()["id"]
    assert api.get(f"{base}/overrides/?current=1").json()["count"] == 1
    now = api.get(f"{base}/now-playing/").json()
    assert now[0]["source"] == "override" and now[0]["layout"].startswith("message:")
    r = api.post(f"{base}/overrides/{oid}/cancel/")
    assert r.json()["state"] == "cancelled"
    assert api.delete(f"{base}/playlists/{pid}/").status_code == 400  # used by a schedule
    sid = api.get(f"{base}/schedules/").json()["results"][0]["id"]
    assert api.delete(f"{base}/schedules/{sid}/").status_code == 204
    assert api.delete(f"{base}/playlists/{pid}/").status_code == 204
    ro = APIClient()
    _t, raw_ro = ServiceToken.issue(name="ro", owner=admin, scopes=["playlists:read"])
    ro.credentials(HTTP_AUTHORIZATION=f"Bearer {raw_ro}")
    assert ro.get(f"{base}/playlists/").status_code == 200
    assert ro.post(f"{base}/playlists/", {"name": "N"}, format="json").status_code == 403
    modules.set_event(event, "schedules", False, user=admin)
    assert api.get(f"{base}/schedules/").status_code == 404
