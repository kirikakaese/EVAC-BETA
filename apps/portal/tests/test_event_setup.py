# SPDX-License-Identifier: AGPL-3.0-or-later
"""Event setup wizard and setup checklist (ADR-0050)."""
import pytest

from apps.accounts.models import TOTPDevice
from apps.content.models import Layout
from apps.core import modules, setup
from apps.core.models import AuditLog
from apps.core.plugins import SetupCheckSpec
from apps.core.registry import registry
from apps.events.models import Event, Invitation
from apps.screens.models import Screen
from apps.venues.models import Point, Zone
from conftest import login_2fa

pytestmark = pytest.mark.django_db


def _basics(client, slug="spring", **extra):
    return client.post("/events/new/", {"name": "Spring Fair", "slug": slug, "timezone": "Europe/Berlin",
                                        "start_date": "2026-05-01", "end_date": "2026-05-03", **extra})


def test_happy_path(admin_client, admin, venue):
    page = admin_client.get("/events/new/").content.decode()
    assert "New event" in page and "Create and continue" in page and 'aria-current="step"' in page
    r = _basics(admin_client)
    assert r.status_code == 302 and r.url == "/e/spring/setup/venue/"
    event = Event.objects.get(slug="spring")
    assert event.memberships.get(user=admin).assignments.get().role.key == "admin"

    # venue: pick the existing one and quick-create another
    assert "Hall" in admin_client.get(r.url).content.decode()
    r = admin_client.post(r.url, {"venues": [str(venue.pk)], "venue-name": "Annex", "venue-slug": "annex",
                                  "venue-timezone": "Europe/Berlin"})
    assert r.url == "/e/spring/setup/modules/"
    assert set(event.venues.values_list("slug", flat=True)) == {"hall", "annex"}

    # event type: festival switches crew on; evacuation waits for its statement
    page = admin_client.get(r.url).content.decode()
    assert "Festival / camp" in page and "Crew &amp; shifts" in page
    r = admin_client.post(r.url, {"preset": "festival"})
    assert r.url == "/e/spring/setup/safety/"
    event = Event.objects.get(slug="spring")
    assert modules.is_enabled("crew", event) and not modules.is_enabled("evacuation", event)

    # safety: statement and two-factor status; nothing happens without ticking the box
    page = admin_client.get(r.url).content.decode()
    assert "DIN 14675" in page and "Your two-factor sign-in" in page and "/accounts/security/" in page
    assert admin_client.post(r.url, {}).url == "/e/spring/setup/safety/"
    assert not modules.is_enabled("evacuation", Event.objects.get(slug="spring"))
    r = admin_client.post(r.url, {"accept_evacuation": "on"})
    assert r.url == "/e/spring/setup/team/"
    event = Event.objects.get(slug="spring")
    assert modules.is_enabled("evacuation", event) and not modules.acknowledgement_needed("evacuation", event)
    assert modules.instance_enabled("evacuation")

    # team: invite someone
    crew = event.roles.get(key="crew")
    assert admin_client.post(r.url, {"email": "Helper@Example.org", "role": str(crew.pk)}).url == r.url
    assert Invitation.objects.filter(event=event, email="helper@example.org").exists()
    assert "Invitation link" in admin_client.get(r.url).content.decode()

    # screens: a template is created and published through the gallery, pairing goes to the screens module
    page = admin_client.get("/e/spring/setup/screens/").content.decode()
    assert "Welcome" in page and "Pair a screen" in page
    r = admin_client.post("/e/spring/content/templates/", {"template": "welcome", "name": "Main screen",
                                                             "publish": "1", "next": "/e/spring/setup/screens/"})
    assert r.url == "/e/spring/setup/screens/"
    layout = Layout.objects.get(event=event)
    assert layout.published is not None and layout.is_default
    r = admin_client.post("/e/spring/setup/screens/", {"code": "abc123", "name": "Foyer"})
    assert r.url.startswith("/e/spring/screens/pair/?code=abc123&name=Foyer&next=%2Fe%2Fspring%2Fsetup%2Fscreens%2F")

    page = admin_client.get("/e/spring/setup/done/").content.decode()
    assert "Ready to go" in page and "supplementary information system" in page
    assert "evac_event_setup" not in admin_client.session or "spring" not in admin_client.session["evac_event_setup"]
    actions = set(AuditLog.objects.for_event(event).values_list("action", flat=True))
    assert {"event.created", "venue.linked", "venue.created", "module.acknowledged", "member.invited",
            "layout.created", "layout.published"} <= actions
    assert AuditLog.objects.filter(action="module.toggled").exists()  # evacuation, at instance level


def test_skip_and_resume(admin_client):
    r = _basics(admin_client, slug="quick", skip_wizard="1")
    assert r.url == "/e/quick/"
    r = _basics(admin_client, slug="slow")
    assert admin_client.post(r.url, {"skip": "1"}).url == "/e/slow/setup/modules/"
    # nothing with a statement chosen: the safety step is left out
    assert admin_client.post("/e/slow/setup/modules/", {"skip": "1"}).url == "/e/slow/setup/team/"
    admin_client.get("/e/slow/setup/team/")
    assert admin_client.get("/e/slow/setup/").url == "/e/slow/setup/team/"  # resumable
    assert admin_client.get("/e/slow/setup/safety/").url == "/e/slow/setup/team/"  # not applicable
    assert admin_client.get("/e/slow/setup/nope/").status_code == 404
    # back to the basics of the existing event
    r = admin_client.post("/e/slow/setup/basics/", {"name": "Slow Fair", "timezone": "UTC"})
    assert r.url == "/e/slow/setup/venue/" and Event.objects.get(slug="slow").name == "Slow Fair"
    assert AuditLog.objects.for_event(Event.objects.get(slug="slow")).filter(action="event.updated").exists()


def test_permissions(client, user, member, event, orga):
    client.force_login(user)
    assert client.get("/events/new/").status_code == 403
    assert client.get("/e/demo/setup/venue/").status_code == 403  # viewer
    assert client.post("/e/demo/settings/checklist/", {"hide": "1"}).status_code == 403
    client.logout()
    assert client.get("/e/demo/setup/").status_code == 302  # to the login page


def test_preset_for_non_superuser_with_module_off_for_the_instance(client, orga, event):
    login_2fa(client, orga)
    page = client.get("/e/demo/setup/modules/").content.decode()
    assert "Only an instance admin can switch it on" in page  # evacuation is off for the instance by default
    r = client.post("/e/demo/setup/modules/", {"preset": "festival"})
    assert r.url == "/e/demo/setup/team/"  # no safety step: evacuation is unavailable
    ev = Event.objects.get(slug="demo")
    assert not modules.instance_enabled("evacuation") and not modules.is_enabled("evacuation", ev)
    assert modules.is_enabled("crew", ev)


def test_screens_only_and_custom_with_dependencies(admin_client, event):
    admin_client.post("/e/demo/setup/modules/", {"preset": "screens"})
    ev = Event.objects.get(slug="demo")
    assert modules.is_enabled("playlists", ev) and not modules.is_enabled("program", ev)
    assert not modules.is_enabled("crew", ev) and modules.is_enabled("extensions", ev)  # unmanaged: untouched
    admin_client.post("/e/demo/setup/modules/", {"preset": "custom", "modules": ["schedules", "program"]})
    ev = Event.objects.get(slug="demo")
    # schedules needs playlists -> content -> screens
    assert all(modules.is_enabled(k, ev) for k in ("schedules", "playlists", "content", "screens", "program"))
    assert not modules.is_enabled("widgets", ev) and not modules.is_enabled("venues", ev)
    assert "Pick an event type" in admin_client.post("/e/demo/setup/modules/", {}, follow=True).content.decode()


def test_safety_step_shows_an_accepted_statement(admin_client, admin, event):
    modules.set_instance("evacuation", True)
    page = admin_client.get("/e/demo/setup/safety/").content.decode()
    assert "I have read the statement" in page
    admin_client.post("/e/demo/setup/safety/", {"skip": "1"})
    assert modules.acknowledgement_needed("evacuation", event)
    admin_client.post("/e/demo/setup/safety/", {"accept_evacuation": "on"})
    page = admin_client.get("/e/demo/setup/safety/").content.decode()
    assert "Accepted for this event by" in page


def test_screens_step_without_screen_modules(admin_client, event):
    modules.set_event(event, "screens", False)
    assert admin_client.get("/e/demo/setup/screens/").url == "/e/demo/setup/done/"
    assert admin_client.post("/e/demo/setup/screens/", {"code": "x"}).url == "/e/demo/setup/done/"


def _keys(event, request=None):
    return {i["key"]: i for i in setup.items(event, request)}


def test_checklist_items_follow_the_event(admin_client, admin, event, venue, other):
    items = _keys(event)
    assert items["venue"]["done"] and not items["venue_map"]["done"]
    assert "no exits" in items["venue_map"]["detail"] and items["venue_map"]["url"] == "/e/demo/venues/hall/map/"
    assert not items["screens"]["done"] and not items["layout"]["done"] and not items["team"]["done"]
    assert not items["two_factor"]["done"] and items["staff_channel"]["optional"]
    assert "evacuation_statement" not in items  # module off: hidden
    page = admin_client.get("/e/demo/").content.decode()
    assert "Set up this event" in page and "Draw zones and exits" in page and "Continue the setup wizard" in page

    Point.objects.create(venue=venue, kind=Point.Kind.EXIT, name="East")
    Screen.objects.create(event=event, name="Foyer", paired_at="2026-07-01T10:00:00Z")
    event.memberships.create(user=other)
    TOTPDevice.objects.create(user=admin, name="App", secret_encrypted="x", confirmed=True)
    modules.set_instance("evacuation", True)
    items = _keys(event)
    assert all(items[k]["done"] for k in ("venue_map", "screens", "team", "two_factor"))
    assert not items["evacuation_statement"]["done"]
    modules.acknowledge(event, "evacuation", user=admin)
    from apps.content import services as content

    content.publish_layout(content.create_layout(event, name="Main", key="main", actor=admin), actor=admin)
    assert setup.card(event, None) is None  # only optional items left: the card goes away
    assert "Set up this event" not in admin_client.get("/e/demo/").content.decode()


def test_checklist_hidden_when_module_off_and_per_event(admin_client, member, event):
    from django.test import Client

    modules.set_event(event, "screens", False)
    assert "screens" not in _keys(event) and "layout" not in _keys(event)
    viewer = Client()
    viewer.force_login(member)
    assert "Set up this event" not in viewer.get("/e/demo/").content.decode()  # viewers do not see it
    assert admin_client.post("/e/demo/settings/checklist/", {"hide": "1"}).url == "/e/demo/"
    assert setup.is_hidden(event) and "Set up this event" not in admin_client.get("/e/demo/").content.decode()
    assert AuditLog.objects.for_event(event).filter(action="settings.changed").exists()
    admin_client.post("/e/demo/settings/checklist/", {"hide": "0"})
    assert not setup.is_hidden(event) and "Set up this event" in admin_client.get("/e/demo/").content.decode()
    assert admin_client.get("/e/demo/settings/checklist/").url == "/e/demo/"


def test_two_factor_item_points_members_to_their_security_page(rf, admin, event, venue):
    rf_request = rf.get("/")
    rf_request.user = admin
    item = _keys(event, rf_request)["two_factor"]
    assert "That includes you" in item["detail"] and item["url"] == "/accounts/security/"
    Zone.objects.filter(venue=venue).delete()
    assert "no zones and no exits" in _keys(event)["venue_map"]["detail"]


def test_a_broken_check_does_not_break_the_overview(admin_client, event, monkeypatch):
    def boom(event, request):
        raise RuntimeError("broken plugin")

    reg = registry.ensure_loaded()
    monkeypatch.setitem(reg.setup_checks, "boom", SetupCheckSpec(key="boom", label="Boom", check=boom))
    monkeypatch.setitem(reg.setup_checks, "gone", SetupCheckSpec(key="gone", label="Gone", check=lambda e, r: None,
                                                                 url_name="nope:nope"))
    monkeypatch.setitem(reg.setup_checks, "bad-url", SetupCheckSpec(key="bad-url", label="Bad", url_name="nope:nope",
                                                                    check=lambda e, r: "todo"))
    items = _keys(event)
    assert "boom" not in items and "gone" not in items and items["bad-url"]["url"] == ""
    assert admin_client.get("/e/demo/").status_code == 200


def test_registry_rejects_duplicate_setup_checks():
    from apps.core.registry import Registry, RegistryError

    r = Registry()
    spec = SetupCheckSpec(key="x", label="X", check=lambda e, req: "done")
    r.setup_check(spec)
    with pytest.raises(RegistryError):
        r.setup_check(spec)
