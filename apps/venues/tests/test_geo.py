# SPDX-License-Identifier: AGPL-3.0-or-later
"""Georeferencing and map tiles (ADR-0028)."""
import io
import json
from unittest import mock

import pytest
from PIL import Image

from apps.core import safefetch, settings_store
from apps.core.models import AuditLog
from apps.venues import geo
from apps.venues.models import Floor, Point
from conftest import login_2fa


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.fixture
def ground(venue):
    return Floor.objects.get(name="Ground")


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "green").save(buf, "PNG")
    return buf.getvalue()


def op(client, event, floor, body):
    url = f"/e/{event.slug}/venues/hall/map/op/?floor={floor.pk if floor else 'outdoors'}"
    return client.post(url, data=json.dumps(body), content_type="application/json")


def own_tiles(admin):
    settings_store.save("maps", "instance", "", {"tile_url": "https://tiles.example.org/{z}/{x}/{y}.png",
                                                  "allow_area_download": True}, user=admin)


def test_frame_math(venue, ground):
    frame = geo.Frame(52.52, 13.405, 30)
    lat, lon = geo.to_geo(frame, 120, -40)
    x, y = geo.to_plan(frame, lat, lon)
    assert (x, y) == pytest.approx((120, -40), abs=1e-6)
    # bearing 90: the plan's "up" faces east, so +x (right) points south
    lat, lon = geo.to_geo(geo.Frame(0, 0, 90), 1000, 0)
    assert lat == pytest.approx(-1000 / geo.EARTH_M_PER_DEG) and lon == pytest.approx(0, abs=1e-9)
    assert geo.tile_of(52.52, 13.405, 10) == (550, 335) and geo.tile_of(0, 0, 0) == (0, 0)
    assert geo.valid_tile(3, 7, 7) and not geo.valid_tile(3, 8, 0) and not geo.valid_tile(21, 0, 0)
    tiles = geo.tiles_for_area([geo.to_geo(frame, x, y) for x in (0, 300) for y in (0, 300)], range(15, 17))
    assert {t[0] for t in tiles} == {15, 16} and len(tiles) < 40
    assert geo.frame_of(venue, ground) is None and geo.frame_of(venue, None) is None
    venue.latitude, venue.longitude = 52.5, 13.4
    ground.geo_lat, ground.geo_lon, ground.geo_rotation = 52.51, 13.41, 12
    assert geo.frame_of(venue, None) == geo.Frame(52.5, 13.4, 0) and geo.frame_of(venue, ground).rotation == 12
    assert geo.public_osm("https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    assert geo.public_osm("https://{s}.tile.openstreetmap.de/{z}/{x}/{y}.png")
    assert not geo.public_osm("https://tiles.example.org/{z}/{x}/{y}.png")
    assert geo.upstream(1, 1, 0) == "https://tile.openstreetmap.org/1/1/0.png"


def test_tile_endpoint(admin_client, admin, settings):
    from django.test import Client

    url = "/maptiles/15/17605/10746.png"
    assert Client().get(url).status_code == 302  # login required
    with mock.patch("apps.venues.tasks.fetch_tile.delay") as delay:
        r = admin_client.get(url)
        assert r.status_code == 503 and r["Retry-After"] == "2" and delay.call_args.args == (15, 17605, 10746)
        admin_client.get(url)
        assert delay.call_count == 1  # queued once per minute
    # the background fetch stores it; then it is served from the cache
    with mock.patch("apps.core.safefetch.get", return_value=safefetch.Fetched(200, png(), "image/png", "")) as get:
        assert geo.fetch_tile(15, 17605, 10746) and get.call_args.args[0].endswith("/15/17605/10746.png")
        assert "EVAC/" in get.call_args.kwargs["headers"]["User-Agent"]
        assert geo.fetch_tile(15, 17605, 10746)  # already there
        assert get.call_count == 1
    r = admin_client.get(url)
    assert r.status_code == 200 and r["Content-Type"] == "image/png" and b"".join(r.streaming_content)[:4] == b"\x89PNG"
    assert admin_client.get("/maptiles/3/9/0.png").status_code == 404
    assert admin_client.get("/maptiles/20/0/0.png").status_code == 404  # above max_zoom
    with mock.patch("apps.core.safefetch.get", side_effect=safefetch.FetchError("down")):
        assert not geo.fetch_tile(15, 1, 1)
    with mock.patch("apps.core.safefetch.get", return_value=safefetch.Fetched(200, b"<html>", "text/html", "")):
        assert not geo.fetch_tile(15, 1, 2)
    assert not geo.fetch_tile(99, 0, 0)
    from apps.venues.tasks import download_area, fetch_tile

    with mock.patch("apps.venues.geo.fetch_tile", return_value=True):
        assert fetch_tile.run(1, 0, 0) is True and download_area.run([[1, 0, 0], [1, 1, 0]]) == 2
    settings_store.save("maps", "instance", "", {"tiles_enabled": False}, user=admin)
    assert admin_client.get(url).status_code == 404 and not geo.fetch_tile(15, 3, 3)


def test_georeference_ops_and_map_data(admin_client, event, venue, ground, admin):
    data = admin_client.get(f"/e/{event.slug}/venues/hall/map/data/?floor={ground.pk}").json()
    assert data["map"]["frame"] is None and data["map"]["tileUrl"] == "/maptiles/{z}/{x}/{y}.png"
    assert data["map"]["attribution"].startswith("©") and data["map"]["rotatable"] and not data["map"]["areaDownload"]
    assert op(admin_client, event, ground, {"op": "georef.move", "dx": 1, "dy": 1}).status_code == 400
    r = op(admin_client, event, ground, {"op": "georef", "lat": 52.52, "lon": 13.405, "rotation": 370})
    assert r.status_code == 200
    ground.refresh_from_db()
    assert (ground.geo_lat, ground.geo_lon, ground.geo_rotation) == (52.52, 13.405, 10)
    # dragging the map 10 m to the right moves the plan's origin 10 m "left" in plan terms
    op(admin_client, event, ground, {"op": "georef.move", "dx": 10, "dy": 0})
    ground.refresh_from_db()
    x, y = geo.to_plan(geo.Frame(52.52, 13.405, 10), ground.geo_lat, ground.geo_lon)
    assert (x, y) == pytest.approx((-10, 0), abs=0.01)
    assert op(admin_client, event, ground, {"op": "georef", "lat": 95, "lon": 0}).status_code == 400
    # outdoors: the venue's own coordinates, no rotation
    op(admin_client, event, None, {"op": "georef", "lat": 48.1, "lon": 11.5, "rotation": 45})
    venue.refresh_from_db()
    assert (float(venue.latitude), float(venue.longitude)) == (48.1, 11.5)
    outdoors = admin_client.get(f"/e/{event.slug}/venues/hall/map/data/?floor=outdoors").json()["map"]
    assert outdoors["frame"] == {"lat": 48.1, "lon": 11.5, "rotation": 0.0} and not outdoors["rotatable"]
    assert AuditLog.objects.filter(action="venue.georeferenced").count() == 3
    settings_store.save("maps", "instance", "", {"tiles_enabled": False}, user=admin)
    assert admin_client.get(f"/e/{event.slug}/venues/hall/map/data/?floor=outdoors").json()["map"] is None


def test_area_download(admin_client, event, venue, ground, admin):
    r = op(admin_client, event, ground, {"op": "map.download"})
    assert r.status_code == 400 and "run yourself" in r.json()["error"]  # public OSM: never
    settings_store.save("maps", "instance", "", {"allow_area_download": True}, user=admin)
    assert not geo.area_download_allowed()  # still the public OSM servers
    own_tiles(admin)
    assert geo.area_download_allowed()
    assert "Align" in op(admin_client, event, ground, {"op": "map.download"}).json()["error"]
    ground.geo_lat, ground.geo_lon = 52.52, 13.405
    ground.plan_file, ground.plan_width, ground.plan_height, ground.metres_per_px = "x.png", 1000, 500, 0.1
    ground.save()
    Point.objects.create(venue=venue, floor=ground, name="Far", x=400, y=10)
    with mock.patch("apps.venues.tasks.download_area.delay") as delay:
        r = op(admin_client, event, ground, {"op": "map.download"})
        assert r.status_code == 200 and r.json()["tiles"] == len(delay.call_args.args[0]) > 0
        assert all(14 <= t[0] <= 19 for t in delay.call_args.args[0])
    with mock.patch.object(geo, "MAX_AREA_TILES", 30), mock.patch("apps.venues.tasks.download_area.delay") as delay:
        r = op(admin_client, event, ground, {"op": "map.download"})
        assert r.json()["tiles"] <= 30
    assert AuditLog.objects.filter(action="venue.map_downloaded").exists()


def test_viewer_cannot_align(client, event, venue, ground, member):
    login_2fa(client, member)
    assert op(client, event, ground, {"op": "georef", "lat": 1, "lon": 1}).status_code == 403
    assert client.get("/maptiles/1/0/0.png").status_code == 503
