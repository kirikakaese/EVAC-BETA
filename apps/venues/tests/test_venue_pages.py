# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from apps.events import services
from apps.venues import access
from apps.venues.models import Building, Floor, Room, Venue, Zone


@pytest.mark.django_db
def test_admin_adds_parts(admin_client, event, venue):
    base = "/e/demo/venues/hall/"
    r = admin_client.post(base, {"part": "building", "building-name": "Annex", "building-order": "2"})
    assert r.status_code == 302
    annex = Building.objects.get(name="Annex")
    admin_client.post(base, {"part": "floor", "floor-building": str(annex.pk), "floor-name": "Roof",
                             "floor-level": "3"})
    roof = Floor.objects.get(name="Roof")
    admin_client.post(base, {"part": "zone", "zone-name": "East", "zone-color": "#123456"})
    east = Zone.objects.get(name="East")
    r = admin_client.post(base, {"part": "room", "room-name": "Lounge", "room-floor": str(roof.pk),
                                 "room-zones": [str(east.pk)], "room-capacity": "20", "room-step_free": "on",
                                 "room-wheelchair_spaces": "2"})
    assert r.status_code == 302
    lounge = Room.objects.get(name="Lounge")
    assert lounge.venue == venue and list(lounge.zones.all()) == [east]
    page = admin_client.get(base).content.decode()
    assert "Lounge" in page and "Roof" in page
    admin_client.post(base, {"part": "venue", "venue-name": "Big Hall", "venue-slug": "hall",
                             "venue-timezone": "Europe/Berlin"})
    assert Venue.objects.get(slug="hall").name == "Big Hall"
    admin_client.post(f"{base}room/{lounge.pk}/delete/")
    admin_client.post(f"{base}floor/{roof.pk}/delete/")
    assert not Room.objects.filter(name="Lounge").exists() and not Floor.objects.filter(name="Roof").exists()
    assert admin_client.post(f"{base}planet/{roof.pk}/delete/").status_code == 403


@pytest.mark.django_db
def test_add_and_link_venues(admin_client, event):
    r = admin_client.post("/e/demo/venues/", {"new-name": "Park", "new-slug": "park", "new-timezone": "UTC"})
    assert r.status_code == 302 and event.venues.filter(slug="park").exists()
    lonely = Venue.objects.create(slug="lonely", name="Lonely")
    assert "Lonely" in admin_client.get("/e/demo/venues/").content.decode()
    admin_client.post("/e/demo/venues/", {"link": str(lonely.pk)})
    assert event.venues.filter(slug="lonely").exists()


@pytest.mark.django_db
def test_viewer_cannot_edit(client, member, event, venue):
    client.force_login(member)
    assert client.get("/e/demo/venues/hall/").status_code == 200
    assert client.post("/e/demo/venues/hall/", {"part": "zone", "zone-name": "X"}).status_code == 403
    z = Zone.objects.get(name="North")
    assert client.post(f"/e/demo/venues/hall/zone/{z.pk}/delete/").status_code == 403
    assert client.get("/e/demo/venues/other/").status_code == 404


@pytest.mark.django_db
def test_scoped_venue_visibility(client, event, other, venue, admin, role):
    annex = Venue.objects.create(slug="annex", name="Annex")
    event.venues.add(annex)
    services.assign_role(event, other, role("viewer"), scope_kind="venue", scope_id=str(annex.pk))
    client.force_login(other)
    page = client.get("/e/demo/venues/").content.decode()
    assert "Annex" in page and "Hall" not in page.split("<main")[1].split("Add a venue")[0]
    assert client.get("/e/demo/venues/hall/").status_code == 403
    assert list(access.visible(other)) == [annex]
    assert not access.allowed(other, annex, "venues.manage")
    assert access.allowed(admin, annex, "venues.manage")
    floor = Floor.objects.first()
    assert not access.allowed(other, floor, "venues.view")
