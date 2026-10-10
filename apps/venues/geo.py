# SPDX-License-Identifier: AGPL-3.0-or-later
"""Georeferencing and map tiles (ADR-0028).

A *frame* places a floor plan on the earth: the latitude/longitude of the plan's top-left corner and the bearing
of the plan's "up" (degrees clockwise from north). Plan coordinates are metres (x right, y down); a local
tangent plane is exact enough for a venue. Outdoors uses the venue's coordinates with bearing 0.

Tiles (slippy-map ``{z}/{x}/{y}``) are cached on disk under ``MEDIA_ROOT/venues/tiles/``. A request for a missing
tile never calls the tile server itself: it queues a background fetch and answers 503 (the editor retries).
Area downloads for offline use are only allowed for a tile server you run yourself; the public OpenStreetMap
servers forbid bulk downloading (https://operations.osmfoundation.org/policies/tiles/).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings

from apps.core import settings_store

EARTH_M_PER_DEG = 111_320.0
MAX_AREA_TILES = 5000
PUBLIC_OSM_HOSTS = ("openstreetmap.org", "openstreetmap.fr", "openstreetmap.de")


@dataclass(frozen=True)
class Frame:
    lat: float
    lon: float
    rotation: float = 0.0


def config() -> dict:
    return settings_store.get("maps")


def frame_of(venue, floor) -> Frame | None:
    if floor is not None:
        if floor.geo_lat is None or floor.geo_lon is None:
            return None
        return Frame(floor.geo_lat, floor.geo_lon, floor.geo_rotation or 0.0)
    if venue.latitude is None or venue.longitude is None:
        return None
    return Frame(float(venue.latitude), float(venue.longitude), 0.0)


def to_geo(frame: Frame, x: float, y: float) -> tuple[float, float]:
    """Plan metres -> (lat, lon)."""
    t = math.radians(frame.rotation)
    east = x * math.cos(t) - y * math.sin(t)
    south = x * math.sin(t) + y * math.cos(t)
    lat = frame.lat - south / EARTH_M_PER_DEG
    lon = frame.lon + east / (EARTH_M_PER_DEG * math.cos(math.radians(frame.lat)))
    return lat, lon


def to_plan(frame: Frame, lat: float, lon: float) -> tuple[float, float]:
    """(lat, lon) -> plan metres."""
    south = (frame.lat - lat) * EARTH_M_PER_DEG
    east = (lon - frame.lon) * EARTH_M_PER_DEG * math.cos(math.radians(frame.lat))
    t = math.radians(frame.rotation)
    return east * math.cos(t) + south * math.sin(t), -east * math.sin(t) + south * math.cos(t)


def tile_of(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    lat = max(min(lat, 85.0511), -85.0511)
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def valid_tile(z: int, x: int, y: int) -> bool:
    return 0 <= z <= 20 and 0 <= x < 2 ** z and 0 <= y < 2 ** z


def tiles_for_area(corners: list[tuple[float, float]], zooms: range) -> list[tuple[int, int, int]]:
    """Every tile covering the lat/lon bounding box of ``corners`` at the given zoom levels."""
    lats, lons = [c[0] for c in corners], [c[1] for c in corners]
    out = []
    for z in zooms:
        x0, y0 = tile_of(max(lats), min(lons), z)
        x1, y1 = tile_of(min(lats), max(lons), z)
        out += [(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    return out


# ------------------------------------------------------------------ tile cache
def tile_url() -> str:
    return str(config().get("tile_url") or "")


def public_osm(url: str) -> bool:
    host = (urlsplit(url.replace("{s}", "a")).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in PUBLIC_OSM_HOSTS)


def area_download_allowed() -> bool:
    cfg = config()
    return bool(cfg.get("tiles_enabled") and cfg.get("allow_area_download") and tile_url()
                and not public_osm(tile_url()))


def cache_dir() -> Path:
    key = hashlib.sha256(tile_url().encode()).hexdigest()[:12]
    return Path(settings.MEDIA_ROOT) / "venues" / "tiles" / key


def tile_path(z: int, x: int, y: int) -> Path:
    return cache_dir() / str(z) / str(x) / f"{y}.png"


def upstream(z: int, x: int, y: int) -> str:
    return tile_url().replace("{s}", "abc"[(x + y) % 3]).replace("{z}", str(z)).replace(
        "{x}", str(x)).replace("{y}", str(y))


def fetch_tile(z: int, x: int, y: int) -> bool:
    """Download one tile into the cache (Celery task body). Returns whether it is cached now."""
    from apps.core import safefetch

    if not valid_tile(z, x, y) or not config().get("tiles_enabled") or not tile_url():
        return False
    path = tile_path(z, x, y)
    if path.exists():
        return True
    import evac

    try:
        # the tile server is configured by an instance admin and may be in the venue LAN
        got = safefetch.get(upstream(z, x, y), allow_private=True, max_bytes=2 * 1024 * 1024,
                            headers={"User-Agent": f"EVAC/{evac.__version__} venue map tile cache"})
    except safefetch.FetchError:
        return False
    if not got.body.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF")):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(got.body)
    tmp.replace(path)
    return True
