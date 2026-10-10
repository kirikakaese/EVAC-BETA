# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation models, live blocking of exits and screen directions (roadmap 3.4, ADR-0030)."""
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.core import settings_store
from apps.core.a11y import check_html
from apps.core.models import AuditLog
from apps.evacuation import services
from apps.evacuation.machine import Model, Refused, State
from apps.evacuation.models import BlockedPoint
from apps.events import services as event_services
from apps.screens.models import Screen
from apps.venues.models import Edge, Floor, Point, Venue
from conftest import login_2fa

from .conftest import tf

URL = "/e/demo/evacuation/"


def use(model):
    settings_store.save("evacuation", "instance", "", {"model": model})


@pytest.fixture
def ground(venue):
    return Floor.objects.get(name="Ground")


@pytest.fixture
def plan(venue, ground, zones):
    """W1 -- W2 -- exit East; assembly point A reached from W1."""
    def pt(name, kind, x, y, floor=ground, zone=None):
        return Point.objects.create(venue=venue, floor=floor, name=name, kind=kind, x=x, y=y, zone=zone)
    p = {"w1": pt("W1", "waypoint", 0, 0), "w2": pt("W2", "waypoint", 20, 0),
         "ex": pt("East", "exit", 40, 0, zone=zones["South"]), "a": pt("Meadow", "assembly", 0, -30, floor=None)}
    for a, b in [("w1", "w2"), ("w2", "ex"), ("w1", "a")]:
        Edge.objects.create(venue=venue, a=p[a], b=p[b])
    return p


@pytest.fixture
def screen(event, venue, ground, zones):
    return Screen.objects.create(event=event, name="Foyer", venue=venue, zone=zones["North"], floor=ground,
                                 position_x=5, position_y=5, facing=180)


def test_default_model_is_staged(event, admin, zones):
    settings_store.save("evacuation", "instance", "", {})
    assert services.config(event).model is Model.STAGED
    with pytest.raises(Refused) as err:
        services.change(event, "attention", zone=zones["North"], actor=admin, request=tf(admin))
    assert err.value.code == "model"
    services.change(event, "attention", actor=admin, request=tf(admin))
    with mock.patch("apps.core.settings_store.get", return_value={"model": "nonsense"}):
        assert services.config(event).model is Model.STAGED


def test_simple_model(event, admin):
    use("simple")
    cfg = services.config(event)
    assert cfg.model is Model.SIMPLE and cfg.enabled == frozenset({State.NORMAL, State.ALL_CLEAR, State.EVACUATE})
    with pytest.raises(Refused):
        services.change(event, "attention", actor=admin, request=tf(admin))
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    services.change(event, "all_clear", actor=admin, request=tf(admin))


def test_switching_model_never_strands_an_alarm(event, admin, zones):
    north = zones["North"]
    services.change(event, "shelter_in_place", zone=north, actor=admin, request=tf(admin))
    use("simple")
    # the zone alarm still shows and can still be ended, but not changed
    assert services.effective_for(event, [str(north.pk)]).state is State.SHELTER
    with pytest.raises(Refused):
        services.change(event, "evacuate", zone=north, actor=admin, request=tf(admin))
    services.change(event, "all_clear", zone=north, actor=admin, request=tf(admin))
    services.change(event, "normal", zone=north, actor=admin, request=tf(admin))


def test_block_and_reopen(event, admin, role, plan, django_capture_on_commit_callbacks):
    ex = plan["ex"]
    with mock.patch("apps.core.webhooks.emit") as emit, django_capture_on_commit_callbacks(execute=True):
        assert services.set_blocked(event, ex, True, actor=admin, request=tf(admin), reason="smoke")
        assert not services.set_blocked(event, ex, True, actor=admin, request=tf(admin))
    assert emit.call_args.args[0] == "evacuation.routes_changed" and emit.call_args.args[1]["blocked"]
    assert services.blocked_ids(event) == {str(ex.pk)} and str(BlockedPoint.objects.get()) == "Exit East blocked"
    assert BlockedPoint.objects.get().evac_scope_chain()[0][0] == "venue"
    assert services.set_blocked(event, ex, False, actor=admin, request=tf(admin))
    assert not services.set_blocked(event, ex, False, actor=admin, request=tf(admin))
    assert AuditLog.objects.filter(action="evacuation.point_blocked").exists()
    assert AuditLog.objects.filter(action="evacuation.point_reopened").exists()
    # scoped: someone limited to zone North may not block an exit in zone South
    u = User.objects.create_user(email="n@example.org", password="pw-12345678x")
    event_services.assign_role(event, u, role("security"), scope_kind="zone", scope_id=str(plan["ex"].zone_id))
    services.set_blocked(event, ex, True, actor=u, request=tf(u))
    other = User.objects.create_user(email="o@example.org", password="pw-12345678x")
    event_services.assign_role(event, other, role("viewer"))
    with pytest.raises(PermissionDenied):
        services.set_blocked(event, ex, False, actor=other, request=tf(other))
    stray = Point.objects.create(venue=Venue.objects.create(slug="x", name="X", timezone="UTC"), name="Stray")
    with pytest.raises(Refused):
        services.set_blocked(event, stray, True, actor=admin)


def test_screen_directions(event, admin, venue, plan, screen, zones):
    services.change(event, "evacuate", zone=zones["North"], actor=admin, request=tf(admin))
    [view] = services.screen_views(event)
    assert view.shown.state is State.EVACUATE and view.zone_ids == [str(zones["North"].pk)]
    g = view.guidance
    assert g.kind.value == "route" and g.toward == str(plan["w1"].pk) and g.target == str(plan["a"].pk)
    # the assembly point is blocked live: the screen now sends people to the east exit
    services.set_blocked(event, plan["a"], True, actor=admin, request=tf(admin))
    [view] = services.screen_views(event)
    assert view.guidance.target == str(plan["ex"].pk)
    # everything blocked: follow staff instructions
    services.set_blocked(event, plan["ex"], True, actor=admin, request=tf(admin))
    assert services.screen_views(event)[0].guidance.kind.value == "follow_staff"
    # a fixed direction overrides the route
    settings_store.save("evacuation_screen", "screen", str(screen.pk), {"hint_text": "Exit B", "hint_arrow": "left"})
    [view] = services.screen_views(event)
    assert view.guidance.kind.value == "hint" and view.guidance.text == "Exit B" and view.guidance.arrow == "left"
    # staged model: no computed routes
    settings_store.save("evacuation_screen", "screen", str(screen.pk), {})
    use("staged")
    assert services.screen_views(event)[0].guidance.kind.value == "none"


def test_screen_without_place_follows_staff(event):
    use("zones")
    Screen.objects.create(event=event, name="Lost")
    assert services.screen_views(event)[0].guidance.kind.value == "follow_staff"


def test_screen_zone_from_room(event, venue, zones):
    room = venue.rooms.get(name="Hall B")
    s = Screen.objects.create(event=event, name="B", room=room)
    [view] = services.screen_views(event)
    assert view.screen == s and view.zone_ids == [str(zones["South"].pk)]


def test_without_screens_app(event):
    with mock.patch("django.apps.apps.is_installed", return_value=False):
        assert services.screen_views(event) == []


def test_page_per_model(admin_client, event, plan, screen, zones):
    html = admin_client.get(URL).content.decode()
    assert check_html(html) == []
    assert "Zones and routes" in html and "Exits and passages" in html and "East" in html and "Foyer" in html
    assert "towards W1" in html and "ahead left" in html
    use("staged")
    html = admin_client.get(URL).content.decode()
    assert "Staged, global" in html and "Exits and passages" not in html and "Zone North" not in html
    assert "without direction" in html
    use("simple")
    html = admin_client.get(URL).content.decode()
    assert "Simple takeover" in html and 'value="attention"' not in html


def test_block_view_and_hint_view(admin_client, event, plan, screen):
    ex = plan["ex"]
    r = admin_client.post(f"{URL}block/", {"point": str(ex.pk), "blocked": "1", "reason": "fire"}, follow=True)
    assert "is blocked" in r.content.decode() and BlockedPoint.objects.filter(point=ex).exists()
    html = admin_client.get(URL).content.decode()
    assert "Open again" in html and "fire" in html
    admin_client.post(f"{URL}block/", {"point": str(ex.pk), "blocked": "0"})
    assert not BlockedPoint.objects.exists()
    for bad in ("nope", "00000000-0000-0000-0000-000000000000"):
        assert "Unknown point" in admin_client.post(f"{URL}block/", {"point": bad}, follow=True).content.decode()
    r = admin_client.post(f"{URL}screens/{screen.pk}/direction/", {"hint_text": "Exit B", "hint_arrow": "left"},
                          follow=True)
    assert "saved" in r.content.decode() and services.hint_of(event, screen) == ("Exit B", "left")
    admin_client.post(f"{URL}screens/{screen.pk}/direction/", {"hint_text": "", "hint_arrow": "sideways"})
    assert services.hint_of(event, screen) == ("", "")
    r = admin_client.post(f"{URL}screens/00000000-0000-0000-0000-000000000000/direction/", {}, follow=True)
    assert "Unknown screen" in r.content.decode()


def test_block_view_permission(client, event, member, plan):
    login_2fa(client, member)
    r = client.post(f"{URL}block/", {"point": str(plan["ex"].pk), "blocked": "1"}, follow=True)
    assert "may not block" in r.content.decode()
    assert client.post(f"{URL}screens/00000000-0000-0000-0000-000000000000/direction/", {}).status_code == 403
