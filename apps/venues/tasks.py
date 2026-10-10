# SPDX-License-Identifier: AGPL-3.0-or-later
from celery import shared_task


@shared_task
def fetch_tile(z: int, x: int, y: int) -> bool:
    from . import geo

    return geo.fetch_tile(z, x, y)


@shared_task
def download_area(tiles: list[list[int]]) -> int:
    """Fetch a prepared list of tiles one after the other (area download for offline use)."""
    from . import geo

    return sum(1 for z, x, y in tiles if geo.fetch_tile(z, x, y))
