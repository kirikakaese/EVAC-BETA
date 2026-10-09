# SPDX-License-Identifier: AGPL-3.0-or-later
"""Remote management of running players: commands, and the screenshots and logs they send back.

A screen may only upload what staff asked for: every request is remembered for two minutes, an upload
without a pending request is refused. Screenshots are decoded and re-encoded (JPEG, at most 1920 px wide)
before they are stored, so no uploaded bytes are ever served as they came.
"""
from __future__ import annotations

import io
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import Screen

REQUEST_TTL = 120
MAX_SCREENSHOT_BYTES = 6 * 1024 * 1024
MAX_LOG_LINES = 300
MAX_LINE = 500
#: commands that expect an upload back
UPLOADS = {"screenshot": "screenshot", "logs": "logs"}


def _key(screen, kind: str) -> str:
    return f"evac:screen:{screen.pk}:wants:{kind}"


def request_upload(screen, kind: str) -> None:
    cache.set(_key(screen, kind), timezone.now().isoformat(), REQUEST_TTL)


def pending(screen, kind: str) -> bool:
    return cache.get(_key(screen, kind)) is not None


def _consume(screen, kind: str) -> bool:
    return cache.delete(_key(screen, kind)) or False


def screenshot_path(screen) -> Path:
    return Path(settings.MEDIA_ROOT) / "screens" / str(screen.pk) / "screenshot.jpg"


class UploadRefused(Exception):
    pass


def store_screenshot(screen: Screen, body: bytes, content_type: str) -> None:
    from PIL import Image, UnidentifiedImageError

    if not pending(screen, "screenshot"):
        raise UploadRefused("No screenshot was requested.")
    if content_type.startswith("application/json"):
        import json

        try:
            error = str(json.loads(body or b"{}").get("error", ""))[:300]
        except ValueError:
            error = "invalid report"
        # store first, then clear the request: a page rendered in between must never see "not pending" without
        # the result (it would stop polling)
        Screen.objects.filter(pk=screen.pk).update(screenshot_error=error or "unknown error")
        _consume(screen, "screenshot")
        return
    if len(body) > MAX_SCREENSHOT_BYTES:
        raise UploadRefused("Too large.")
    try:
        img = Image.open(io.BytesIO(body))
        if img.format not in ("JPEG", "PNG", "WEBP"):
            raise UploadRefused("Unsupported image type.")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise UploadRefused("Not an image.") from exc
    img = img.convert("RGB")
    if img.width > 1920:
        img.thumbnail((1920, 1920))
    path = screenshot_path(screen)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    img.save(tmp, "JPEG", quality=82)
    tmp.replace(path)
    Screen.objects.filter(pk=screen.pk).update(screenshot_at=timezone.now(), screenshot_error="")
    _consume(screen, "screenshot")


def store_logs(screen: Screen, lines) -> None:
    if not pending(screen, "logs"):
        raise UploadRefused("No logs were requested.")
    if not isinstance(lines, list):
        raise UploadRefused("Expected a list of lines.")
    clean = [str(line)[:MAX_LINE] for line in lines[-MAX_LOG_LINES:]]
    Screen.objects.filter(pk=screen.pk).update(logs=clean, logs_at=timezone.now())
    _consume(screen, "logs")


def delete_files(screen) -> None:
    screenshot_path(screen).unlink(missing_ok=True)
