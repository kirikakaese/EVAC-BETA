# SPDX-License-Identifier: AGPL-3.0-or-later
"""Map editor (ADR-0027): floor plans, map data, edit operations and the screens layer."""
import io
import json
from unittest import mock

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.events import services as event_services
from apps.screens.models import Screen
from apps.venues import plans
from apps.venues.models import Edge, Floor, Point, Zone
from conftest import login_2fa


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def _png(w=400, h=200, fmt="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (240, 240, 240)).save(buf, fmt)
    return buf.getvalue()


@pytest.fixture
def ground(venue):
    return Floor.objects.get(name="Ground")


def base(event):
    return f"/e/{event.slug}/venues/hall/"


def op(client, event, floor, body):
    url = f"{base(event)}map/op/?floor={floor.pk if floor else 'outdoors'}"
    return client.post(url, data=json.dumps(body), content_type="application/json")


# ------------------------------------------------------------------ plans
def test_plan_upload_formats_and_scale(admin_client, event, venue, ground, media_root):
    url = f"{base(event)}floors/{ground.pk}/plan/upload/"
    r = admin_client.post(url, {"plan": SimpleUploadedFile("plan.png", _png())})
    assert r.status_code == 302 and r["Location"].endswith(f"?floor={ground.pk}")
    ground.refresh_from_db()
    assert ground.plan_file.endswith(".png") and (ground.plan_width, ground.plan_height) == (400, 200)
    assert ground.metres_per_px == pytest.approx(0.25) and not ground.plan_scaled
    served = admin_client.get(f"{base(event)}floors/{ground.pk}/plan/")
    assert served.status_code == 200 and served["Content-Type"] == "image/png"
    assert "default-src 'none'" in served["Content-Security-Policy"]
    first = ground.plan_file

    # SVG: sanitised, size from the viewBox
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 300"><script>alert(1)</script>' \
          b'<rect width="10" height="10" onclick="x()"/></svg>'
    admin_client.post(url, {"plan": SimpleUploadedFile("plan.svg", svg)})
    ground.refresh_from_db()
    stored = plans.path_of(ground).read_bytes()
    assert ground.plan_file.endswith(".svg") and b"script" not in stored and b"onclick" not in stored
    assert (ground.plan_width, ground.plan_height) == (800, 300)
    assert not (media_root / "venues" / "plans" / first).exists()  # replaced file is gone
    assert admin_client.get(f"{base(event)}floors/{ground.pk}/plan/")["Content-Type"] == "image/svg+xml"

    # big pictures are scaled down, JPEG becomes PNG
    with mock.patch.object(plans, "MAX_PX", 300):
        admin_client.post(url, {"plan": SimpleUploadedFile("plan.jpg", _png(600, 300, "JPEG"))})
    ground.refresh_from_db()
    assert (ground.plan_width, ground.plan_height) == (300, 150) and ground.plan_file.endswith(".png")

    # errors are messages, not crashes
    for name, data, text in [("x.txt", b"hello", "not a picture"),
                             ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "viewBox"),
                             ("x.svg", b"<svg><unclosed>", "cannot be used")]:
        r = admin_client.post(url, {"plan": SimpleUploadedFile(name, data)}, follow=True)
        assert text in r.content.decode(), name
    with mock.patch.object(plans, "MAX_BYTES", 10):
        r = admin_client.post(url, {"plan": SimpleUploadedFile("p.png", _png())}, follow=True)
        assert "at most 40 MB" in r.content.decode()

    # remove
    admin_client.post(url, {"remove": "1"})
    ground.refresh_from_db()
    assert ground.plan_file == "" and admin_client.get(f"{base(event)}floors/{ground.pk}/plan/").status_code == 404
    assert AuditLog.objects.filter(action__in=["venue.plan_uploaded", "venue.plan_removed"]).count() >= 4


def test_pdf_plans(admin_client, event, venue, ground):
    pdf = io.BytesIO()
    Image.new("RGB", (300, 200), (255, 255, 255)).save(pdf, "PDF")
    url = f"{base(event)}floors/{ground.pk}/plan/upload/"
    with mock.patch.object(plans, "has_pdf_renderer", return_value=False):
        r = admin_client.post(url, {"plan": SimpleUploadedFile("plan.pdf", pdf.getvalue())}, follow=True)
        assert "poppler" in r.content.decode()
    if plans.has_pdf_renderer():
        admin_client.post(url, {"plan": SimpleUploadedFile("plan.pdf", pdf.getvalue())})
        ground.refresh_from_db()
        assert ground.plan_file.endswith(".png") and ground.plan_width > 300  # rendered at 150 dpi
        with mock.patch("apps.venues.plans.subprocess.run", side_effect=OSError):
            r = admin_client.post(url, {"plan": SimpleUploadedFile("plan.pdf", pdf.getvalue())}, follow=True)
            assert "could not be read" in r.content.decode()


def test_scale_keeps_drawings_in_place(admin_client, event, venue, ground, admin):
    plans.store(ground, SimpleUploadedFile("plan.png", _png(200, 100)), actor=admin)
    ground.refresh_from_db()
    assert ground.metres_per_px == pytest.approx(0.5)
    p = Point.objects.create(venue=venue, floor=ground, kind="exit", name="E", x=10, y=20)
    other = Point.objects.create(venue=venue, floor=None, kind="assembly", name="Outside", x=10, y=20)
    north = Zone.objects.get(name="North")
    north.areas = [{"floor": str(ground.pk), "points": [[0, 0], [10, 0], [10, 10]]},
                   {"floor": None, "points": [[0, 0], [1, 0], [1, 1]]}]
    north.save()
    screen = Screen.objects.create(event=event, name="Foyer", venue=venue, floor=ground, position_x=4, position_y=6)
    # 40 px are 10 m: 0.25 m/px instead of 0.5, so everything on this floor halves
    r = op(admin_client, event, ground, {"op": "scale", "px": 40, "metres": 10})
    assert r.json() == {"ok": True}
    for obj in (p, other, north, screen, ground):
        obj.refresh_from_db()
    assert (p.x, p.y) == (5, 10) and (other.x, other.y) == (10, 20)
    assert north.areas[0]["points"][1] == [5, 0] and north.areas[1]["points"][1] == [1, 0]
    assert (screen.position_x, screen.position_y) == (2, 3) and ground.plan_scaled
    assert op(admin_client, event, ground, {"op": "scale", "px": 0, "metres": 1}).status_code == 400
    assert op(admin_client, event, None, {"op": "scale", "px": 1, "metres": 1}).status_code == 400


# ------------------------------------------------------------------ page, data, operations
def test_map_page_and_data(admin_client, event, venue, ground):
    page = admin_client.get(f"{base(event)}map/")
    assert page.status_code == 200 and b"evac-map-editor" in page.content and b"map-config" in page.content
    assert audit_url(admin_client, f"{base(event)}map/") == []
    assert admin_client.get(f"{base(event)}map/?floor=outdoors").status_code == 200
    assert admin_client.get(f"{base(event)}map/?floor=nope").status_code == 404
    assert admin_client.get(f"{base(event)}map/data/?floor=nope").status_code == 404
    Point.objects.create(venue=venue, floor=ground, kind="exit", name="Exit A", x=20, y=0)
    Point.objects.create(venue=venue, floor=None, kind="assembly", name="Car park", x=60, y=0)
    a, b = Point.objects.order_by("name")
    Edge.objects.create(venue=venue, a=b, b=a)
    data = admin_client.get(f"{base(event)}map/data/?floor={ground.pk}").json()
    assert [p["name"] for p in data["points"]] == ["Exit A"] and data["canEdit"]
    assert data["points"][0]["next"] == str(a.pk) and not data["points"][0]["noWayOut"]
    assert data["edges"][0]["elsewhere"] == "outdoors" and data["elsewhere"][str(a.pk)]["name"] == "Car park"
    assert data["plan"] is None and {f["label"] for f in data["floors"]} >= {"Main · Ground"}
    assert data["layers"][0]["key"] == "screens"
    outside = admin_client.get(f"{base(event)}map/data/?floor=outdoors").json()
    assert [p["name"] for p in outside["points"]] == ["Car park"]


def test_map_operations(admin_client, event, venue, ground):
    def ok(body):
        r = op(admin_client, event, ground, body)
        assert r.status_code == 200, r.content
        return r.json()

    a = ok({"op": "point.add", "kind": "exit", "x": 1.23456, "y": 2})["id"]
    b = ok({"op": "point.add", "kind": "stairs", "name": "North stairs", "x": 10, "y": 2})["id"]
    pa, pb = Point.objects.get(pk=a), Point.objects.get(pk=b)
    assert (pa.name, pa.x, pa.floor) == ("Exit", 1.235, ground) and not pb.step_free
    north = Zone.objects.get(name="North")
    ok({"op": "point.update", "id": a, "x": 5, "name": "Main exit", "kind": "assembly", "stepFree": False,
        "zone": str(north.pk)})
    pa.refresh_from_db()
    assert (pa.x, pa.name, pa.kind, pa.step_free, pa.zone) == (5, "Main exit", "assembly", False, north)
    ok({"op": "point.update", "id": a, "zone": None})
    e = ok({"op": "edge.add", "a": a, "b": b})["id"]
    assert not Edge.objects.get(pk=e).step_free  # stairs: not step-free
    ok({"op": "edge.update", "id": e, "oneWay": True, "stepFree": True})
    assert Edge.objects.get(pk=e).one_way
    ok({"op": "zone.area", "zone": str(north.pk), "points": [[0, 0], [10, 0], [10, 10]]})
    north.refresh_from_db()
    assert north.areas == [{"floor": str(ground.pk), "points": [[0, 0], [10, 0], [10, 10]]}]
    data = admin_client.get(f"{base(event)}map/data/?floor={ground.pk}").json()
    assert next(z for z in data["zones"] if z["name"] == "North")["area"] == [[0, 0], [10, 0], [10, 10]]
    ok({"op": "zone.area", "zone": str(north.pk), "points": []})
    north.refresh_from_db()
    assert north.areas == []
    for bad, text in [({"op": "edge.add", "a": a, "b": a}, "two different"),
                      ({"op": "edge.add", "a": b, "b": a}, "already"),
                      ({"op": "point.update", "id": "nope"}, "Unknown point"),
                      ({"op": "point.add", "x": "a", "y": 1}, "number"),
                      ({"op": "point.add", "x": 1e9, "y": 1}, "out of range"),
                      ({"op": "edge.delete", "id": ""}, "Unknown"), ({"op": "edge.update", "id": "nope"}, "Unknown"),
                      ({"op": "zone.area", "zone": str(north.pk), "points": [[0, 0]]}, "three corners"),
                      ({"op": "zone.area", "zone": "nope"}, "Unknown zone"),
                      ({"op": "layer.place", "layer": "x"}, "layer"), ({"op": "warp"}, "Unknown operation")]:
        r = op(admin_client, event, ground, bad)
        assert r.status_code == 400 and text in r.json()["error"], bad
    r = admin_client.post(f"{base(event)}map/op/?floor={ground.pk}", data="[1]", content_type="application/json")
    assert r.status_code == 400
    ok({"op": "edge.delete", "id": e})
    ok({"op": "point.delete", "id": b})
    assert not Edge.objects.exists() and Point.objects.count() == 1
    assert AuditLog.objects.filter(action="venue.map_edited").exists()


def test_screens_layer(admin_client, event, venue, ground, client, role):
    s = Screen.objects.create(event=event, name="Foyer screen")
    data = admin_client.get(f"{base(event)}map/data/?floor={ground.pk}").json()
    item = data["layers"][0]["items"][0]
    assert item["label"] == "Foyer screen" and not item["placed"]
    r = op(admin_client, event, ground, {"op": "layer.place", "layer": "screens", "id": str(s.pk), "x": 3, "y": 4,
                                         "facing": 450})
    assert r.status_code == 200
    s.refresh_from_db()
    assert (s.floor, s.position_x, s.position_y, s.facing, s.venue) == (ground, 3, 4, 90, venue)
    assert AuditLog.objects.filter(action="screen.placed").exists()
    other_floor = admin_client.get(f"{base(event)}map/data/?floor=outdoors").json()
    assert other_floor["layers"][0]["items"] == []  # placed elsewhere: not offered on another floor
    op(admin_client, event, ground, {"op": "layer.place", "layer": "screens", "id": str(s.pk), "x": None})
    s.refresh_from_db()
    assert s.position_x is None and s.floor is None
    assert op(admin_client, event, ground, {"op": "layer.place", "layer": "screens", "id": "nope", "x": 1, "y": 1}
              ).status_code == 400
    # someone who may edit venues but not screens
    from apps.accounts.models import User

    planner = User.objects.create_user(email="planner@example.org", password="pw-planner-1234")
    plan_role = event.roles.create(key="planner", name="Planner", permissions=["venues.view", "venues.manage"])
    event_services.assign_role(event, planner, plan_role)
    login_2fa(client, planner)
    r = op(client, event, ground, {"op": "layer.place", "layer": "screens", "id": str(s.pk), "x": 1, "y": 1})
    assert r.status_code == 403
    assert op(client, event, ground, {"op": "point.add", "x": 1, "y": 1}).status_code == 200


def test_permissions_and_module(client, event, venue, ground, member, admin):
    login_2fa(client, member)  # viewer: may look, not edit
    assert client.get(f"{base(event)}map/").status_code == 200
    data = client.get(f"{base(event)}map/data/?floor={ground.pk}").json()
    assert not data["canEdit"] and not data["layers"][0]["editable"]
    assert op(client, event, ground, {"op": "point.add", "x": 1, "y": 1}).status_code == 403
    assert client.post(f"{base(event)}floors/{ground.pk}/plan/upload/", {"remove": "1"}).status_code == 403
    from apps.core import modules

    modules.set_event(event, "screens", False, user=admin)
    login_2fa(client, admin)
    assert client.get(f"{base(event)}map/data/?floor={ground.pk}").json()["layers"] == []
