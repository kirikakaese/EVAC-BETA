# SPDX-License-Identifier: AGPL-3.0-or-later
"""Crew & shifts (ADR-0041): sign-up rules, check-in by QR, no-shows, "needed now", pages, permissions, API."""
import datetime as dt
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core import modules, settings_store
from apps.core.a11y import check_html
from apps.crew import panels, presets, services
from apps.crew.models import Assignment, Member, Shift, Skill, Team
from apps.events import services as ev
from conftest import login_2fa

pytestmark = pytest.mark.django_db
NOW = timezone.now().replace(microsecond=0)


@pytest.fixture
def team(event, admin):
    return services.save_team(Team(event=event, name="Entrance", colour="#2563eb"), actor=admin)


def shift(event, team, start_h=1.0, hours=3.0, needed=2, title="Gate", **kw):
    return services.save_shift(Shift(event=event, team=team, title=title, needed=needed,
                                     starts_at=NOW + dt.timedelta(hours=start_h),
                                     ends_at=NOW + dt.timedelta(hours=start_h + hours), **kw), actor=None)


def person(event, name="Ada", **kw):
    return services.save_member(Member(event=event, name=name, **kw), actor=None)


def test_sign_up_rules(event, team, admin):
    s = shift(event, team, needed=1)
    ada, bob = person(event), person(event, "Bob")
    a = services.sign_up(s, ada, actor=admin)
    assert services.sign_up(s, ada, actor=admin) == a  # idempotent
    with pytest.raises(ValidationError, match="full"):
        services.sign_up(s, bob, actor=admin)
    forced = services.sign_up(s, bob, actor=admin, force=True)
    assert forced.status == "signed_up"
    from apps.core.models import AuditLog
    assert AuditLog.objects.filter(action="crew.signed_up_forced").exists()
    # overlap and rest
    s2 = shift(event, team, start_h=2, title="Overlap")
    assert any("overlaps" in p for p in services.problems(s2, ada))
    s3 = shift(event, team, start_h=4.25, title="Too soon")
    assert any("rest" in p for p in services.problems(s3, ada))
    # too many hours a day
    settings_store.save("crew", "event", str(event.pk), {"max_hours_per_day": 5}, event=event)
    s4 = shift(event, team, start_h=5, hours=8, title="Long")
    assert any("hours" in p for p in services.problems(s4, ada))
    # skills
    fa = Skill.objects.create(event=event, name="First aid")
    s5 = shift(event, team, start_h=20, title="Medic")
    s5.skills.add(fa)
    assert any("First aid" in p for p in services.problems(s5, ada))
    ada.skills.add(fa)
    assert not any("First aid" in p for p in services.problems(s5, ada))
    # started long ago
    old = shift(event, team, start_h=-2, title="Old")
    assert any("started" in p for p in services.problems(old, bob))


def test_cancel_window_and_members_of_other_events(event, team, admin, venue):
    far, near = shift(event, team, start_h=5, title="Far"), shift(event, team, start_h=0.5, title="Near")
    ada = person(event)
    services.cancel(services.sign_up(far, ada, actor=admin), actor=admin)
    a = services.sign_up(near, ada, actor=admin)
    with pytest.raises(ValidationError, match="Too close"):
        services.cancel(a, actor=admin)
    services.cancel(a, actor=admin, force=True)
    assert not Assignment.objects.exists()
    other = ev.create_event(name="Other", slug="other", user=admin)
    with pytest.raises(ValidationError):
        services.sign_up(far, person(other, "Zed"), actor=admin)


def test_scan_walk_in_check_in_out(event, team, user, member):
    s = shift(event, team, start_h=-0.1)
    what, a = services.scan(s, user)
    assert what == "in" and a.status == "checked_in" and a.source == "qr"
    assert Member.objects.get(user=user).arrived
    assert services.scan(s, user)[0] == "out"
    assert services.scan(s, user)[0] == "done"
    a.refresh_from_db()
    with pytest.raises(ValidationError):
        services.check_out(a, actor=user)


def test_no_shows_notify_leads_and_reopen(event, team, admin, django_capture_on_commit_callbacks):
    team.leads.add(admin)
    s = shift(event, team, start_h=-0.5, needed=1)
    a = services.sign_up(s, person(event), actor=admin, force=True)
    assert services.needed_now(event) == [] or all(n["id"] != str(s.pk) for n in services.needed_now(event))
    with mock.patch("apps.core.webhooks.emit") as emit:
        assert services.mark_no_shows(NOW + dt.timedelta(minutes=1)) == 1
    a.refresh_from_db()
    assert a.status == "no_show"
    assert emit.call_args[0][0] == "crew.no_show"
    from apps.core.models import Notification
    assert Notification.objects.filter(user=admin, title__startswith="No-show").exists()
    gap = [n for n in services.needed_now(event) if n["id"] == str(s.pk)]
    assert gap and gap[0]["missing"] == 1 and gap[0]["now"]
    # a no-show who turns up after all
    a2 = services.sign_up(s, a.member, actor=admin, force=True)
    assert a2.pk == a.pk and a2.status == "signed_up"
    assert services.mark_no_shows(NOW + dt.timedelta(minutes=2)) == 1  # still late: no-show again


def test_ops_log_line_for_no_show(event, team, admin):
    from apps.ops import services as ops
    from apps.ops.models import LogEntry

    ops.sink("crew.no_show", {"member": "Ada", "title": "Gate", "missing": 1}, event)
    assert LogEntry.objects.filter(event=event, text__contains="No-show: Ada").exists()


def test_needed_now_and_sources(event, team, admin):
    s = shift(event, team, start_h=0.5, needed=3)
    services.sign_up(s, person(event), actor=admin)
    shift(event, team, start_h=8, title="Later")  # beyond the window
    rows = services.needed_now(event)
    assert [r["title"] for r in rows] == ["Gate"] and rows[0]["missing"] == 2 and not rows[0]["now"]
    assert panels.needed_now_source(event)["missing"] == 2
    board = panels.board_source(event)["items"]
    assert any(i["title"] == "Gate" for i in board)


def test_presets_install_feeds_and_widgets(event, admin):
    modules.set_instance("widgets", True)
    made = presets.install(event, actor=admin)
    assert {w.name for w in made} == {"Crew: needed now", "Crew: shift board"}
    assert presets.install(event, actor=admin) == []


def test_pages_and_actions(client, event, team, admin):
    c = login_2fa(client, admin)
    s = shift(event, team, start_h=-0.1)
    ada = person(event)
    a = services.sign_up(s, ada, actor=admin, force=True)
    base = f"/e/{event.slug}/crew/"
    for url in ["", f"?day={s.starts_at.date()}&team={team.pk}", f"shifts/{s.pk}/", f"shifts/{s.pk}/?print=1",
                f"shifts/{s.pk}/edit/", "shifts/new/", "teams/", "members/new/", f"members/{ada.pk}/",
                f"scan/{s.checkin_token}/"]:
        r = c.get(base + url)
        assert r.status_code == 200, url
        assert check_html(r.content.decode()) == [], url
    assert b"<svg" in c.get(f"{base}shifts/{s.pk}/").content
    c.post(f"{base}people/{a.pk}/", {"action": "in"})
    a.refresh_from_db()
    assert a.status == "checked_in"
    c.post(f"{base}people/{a.pk}/", {"action": "out"})
    a.refresh_from_db()
    assert a.status == "done"
    # new shift, team, skill, member through the forms
    r = c.post(base + "shifts/new/", {"team": team.pk, "title": "Bar", "starts_at": "2030-01-01T10:00",
                                      "ends_at": "2030-01-01T12:00", "needed": 2, "open_signup": "on"})
    assert r.status_code == 302 and Shift.objects.filter(title="Bar").exists()
    c.post(base + "teams/", {"what": "team", "team-name": "Bar", "team-colour": "#ca8a04"})
    c.post(base + "teams/", {"what": "skill", "skill-name": "Forklift"})
    assert Team.objects.filter(name="Bar").exists() and Skill.objects.filter(name="Forklift").exists()
    r = c.post(base + "members/new/", {"name": "Grace", "teams": [team.pk]})
    assert r.status_code == 302 and Member.objects.filter(name="Grace").exists()
    c.post(f"{base}shifts/{s.pk}/", {"what": "add", "member": Member.objects.get(name="Grace").pk, "force": "1"})
    assert Assignment.objects.filter(shift=s, member__name="Grace").exists()
    bar = Shift.objects.get(title="Bar")
    assert c.post(f"{base}shifts/{bar.pk}/delete/").status_code == 302
    assert not Shift.objects.filter(title="Bar").exists()


def test_staff_app_sign_up_check_in_cancel(client, event, team, user, role):
    ev.assign_role(event, user, role("crew"))
    client.force_login(user)
    s = shift(event, team, start_h=0.05, needed=2)
    later = shift(event, team, start_h=6, title="Later")
    r = client.get(f"/e/{event.slug}/staff/")
    assert r.status_code == 200 and b"Help needed" in r.content
    client.post(f"/e/{event.slug}/crew/shifts/{s.pk}/signup/", {"next": f"/e/{event.slug}/staff/"})
    a = Assignment.objects.get(shift=s)
    client.post(f"/e/{event.slug}/crew/mine/{a.pk}/", {"action": "in"})
    a.refresh_from_db()
    assert a.status == "checked_in"
    client.post(f"/e/{event.slug}/crew/mine/{a.pk}/", {"action": "in"})  # offline replay: harmless
    client.post(f"/e/{event.slug}/crew/shifts/{later.pk}/signup/")
    b = Assignment.objects.get(shift=later)
    client.post(f"/e/{event.slug}/crew/mine/{b.pk}/", {"action": "cancel"})
    assert not Assignment.objects.filter(pk=b.pk).exists()
    # crew without crew.manage cannot edit or check in others
    assert client.get(f"/e/{event.slug}/crew/shifts/new/").status_code == 403
    assert client.post(f"/e/{event.slug}/crew/people/{a.pk}/", {"action": "out"}).status_code == 403


def test_team_lead_manages_own_team_only(client, event, team, user, member):
    other = services.save_team(Team(event=event, name="Bar"), actor=None)
    team.leads.add(user)
    client.force_login(user)
    s, o = shift(event, team), shift(event, other, title="Bar shift")
    assert client.get(f"/e/{event.slug}/crew/shifts/{s.pk}/edit/").status_code == 200
    assert client.get(f"/e/{event.slug}/crew/shifts/{o.pk}/edit/").status_code == 403


def test_module_off_hides_pages(client, event, admin):
    c = login_2fa(client, admin)
    modules.set_instance("crew", False)
    assert c.get(f"/e/{event.slug}/crew/").status_code == 404
    assert c.get(f"/api/v1/events/{event.slug}/shifts/").status_code == 404


def test_api(client, event, team, admin):
    c = login_2fa(client, admin)
    s = shift(event, team, start_h=0.5)
    services.sign_up(s, person(event), actor=admin)
    r = c.get(f"/api/v1/events/{event.slug}/shifts/")
    assert r.status_code == 200 and r.json()["results"][0]["filled"] == 1
    day = s.starts_at.astimezone(services._tz(event)).date()
    assert c.get(f"/api/v1/events/{event.slug}/shifts/?day={day}").json()["count"] == 1
    assert c.get(f"/api/v1/events/{event.slug}/shifts/?day=x").status_code == 400
    assert c.get(f"/api/v1/events/{event.slug}/shifts/needed/").json()[0]["missing"] == 1
    assert c.get(f"/api/v1/events/{event.slug}/crew-teams/").json()["results"][0]["name"] == "Entrance"


def test_scope_and_audience(event, team, admin, user):
    from apps.core.registry import registry
    from apps.crew import evac_plugin  # noqa: F401

    reg = registry.ensure_loaded()
    assert "team" in reg.scope_kinds
    m = person(event, user=user)
    m.teams.add(team)
    assert user in panels.team_members(event, {str(team.pk)})
    assert team.evac_scope_chain() == [("team", str(team.pk))]
