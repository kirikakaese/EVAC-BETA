# SPDX-License-Identifier: AGPL-3.0-or-later
"""Floor plans for the map editor (ADR-0027): PNG, JPEG, WebP, SVG or the first page of a PDF.

Raster plans are re-encoded as PNG (at most ``MAX_PX`` on the longer side), SVG plans are sanitised, PDFs are
rendered with ``pdftoppm`` (poppler-utils, in the Docker image) when it is installed. Files are stored by
content hash under ``MEDIA_ROOT/venues/plans/``.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from PIL import Image, UnidentifiedImageError

from apps.core import svg
from apps.core.audit import log

MAX_BYTES = 40 * 1024 * 1024
MAX_PX = 8000
PDF_DPI = 150
Image.MAX_IMAGE_PIXELS = max(Image.MAX_IMAGE_PIXELS or 0, 200_000_000)


def directory() -> Path:
    path = Path(settings.MEDIA_ROOT) / "venues" / "plans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def path_of(floor) -> Path | None:
    if not floor.plan_file or "/" in floor.plan_file:
        return None
    p = directory() / floor.plan_file
    return p if p.exists() else None


def has_pdf_renderer() -> bool:
    return shutil.which("pdftoppm") is not None


def _read(upload) -> bytes:
    data = bytearray()
    for chunk in (upload.chunks() if hasattr(upload, "chunks") else [upload.read()]):
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise ValidationError(_("Floor plans may be at most 40 MB."))
    return bytes(data)


def _pdf_to_png(data: bytes) -> bytes:
    if not has_pdf_renderer():
        raise ValidationError(_("PDF plans need poppler-utils (pdftoppm) on the server; upload a PNG or SVG."))
    with tempfile.TemporaryDirectory(prefix="evac-plan-") as tmp:
        src = Path(tmp) / "plan.pdf"
        src.write_bytes(data)
        try:
            subprocess.run(["pdftoppm", "-png", "-r", str(PDF_DPI), "-f", "1", "-l", "1", "-singlefile",
                            str(src), str(Path(tmp) / "page")], check=True, capture_output=True, timeout=120)
        except (subprocess.SubprocessError, OSError):
            raise ValidationError(_("This PDF could not be read.")) from None
        return (Path(tmp) / "page.png").read_bytes()


def _raster(data: bytes) -> tuple[bytes, int, int]:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError(_("This file is not a picture, SVG or PDF.")) from None
    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    if max(im.size) > MAX_PX:
        im.thumbnail((MAX_PX, MAX_PX))
    out = io.BytesIO()
    im.save(out, "PNG", optimize=True)
    return out.getvalue(), im.width, im.height


def process(data: bytes, name: str) -> tuple[bytes, str, int, int]:
    """Plan bytes, extension and size (px) from an upload."""
    lower = name.lower()
    if lower.endswith(".svg") or data.lstrip()[:5] in (b"<?xml", b"<svg "):
        try:
            clean = svg.sanitize_svg(data)
            size = svg.size(clean)
        except Exception:  # noqa: BLE001 - any parser error: not a usable SVG
            raise ValidationError(_("This SVG file cannot be used.")) from None
        if not size or size[0] <= 0 or size[1] <= 0:
            raise ValidationError(_("The SVG needs a width and height or a viewBox."))
        return clean, "svg", round(size[0]), round(size[1])
    if lower.endswith(".pdf") or data[:5] == b"%PDF-":
        data = _pdf_to_png(data)
    png, w, h = _raster(data)
    return png, "png", w, h


def store(floor, upload, *, actor, request=None, event=None) -> None:
    data, ext, width, height = process(_read(upload), getattr(upload, "name", "") or "")
    name = f"{hashlib.sha256(data).hexdigest()}.{ext}"
    (directory() / name).write_bytes(data)
    old = floor.plan_file
    floor.plan_file, floor.plan_width, floor.plan_height = name, width, height
    if not floor.plan_scaled:
        floor.metres_per_px = 100.0 / max(width, 1)  # until measured: the plan is 100 m wide
    floor.save(update_fields=["plan_file", "plan_width", "plan_height", "metres_per_px"])
    log(action="venue.plan_uploaded", actor=actor, target=floor, event=event, request=request,
        message=f"Floor plan for {floor} uploaded ({width}×{height})")
    _gc(old)


def remove(floor, *, actor, request=None, event=None) -> None:
    old = floor.plan_file
    floor.plan_file, floor.plan_width, floor.plan_height = "", 0, 0
    floor.save(update_fields=["plan_file", "plan_width", "plan_height"])
    log(action="venue.plan_removed", actor=actor, target=floor, event=event, request=request,
        message=f"Floor plan for {floor} removed")
    _gc(old)


def set_scale(floor, *, px: float, metres: float, actor, request=None, event=None) -> None:
    """``px`` plan pixels are ``metres`` long."""
    if px <= 0 or metres <= 0:
        raise ValidationError(_("Measure a line of some length."))
    before = floor.metres_per_px
    floor.metres_per_px, floor.plan_scaled = metres / px, True
    floor.save(update_fields=["metres_per_px", "plan_scaled"])
    if before > 0:
        _rescale(floor, floor.metres_per_px / before)
    log(action="venue.plan_scaled", actor=actor, target=floor, event=event, request=request,
        changes={"metres_per_px": [before, floor.metres_per_px]})


def _rescale(floor, factor: float) -> None:
    """Keep everything on the plan where it was drawn: positions are metres, so they scale with the plan."""
    from apps.core.registry import registry

    from .models import Point, Zone

    for p in Point.objects.filter(floor=floor):
        p.x, p.y = p.x * factor, p.y * factor
        p.save(update_fields=["x", "y"])
    for zone in Zone.objects.filter(venue_id=floor.building.venue_id):
        changed = False
        for area in zone.areas or []:
            if area.get("floor") == str(floor.pk):
                area["points"] = [[x * factor, y * factor] for x, y in area.get("points", [])]
                changed = True
        if changed:
            zone.save(update_fields=["areas"])
    for spec in registry.ensure_loaded().map_layers.values():
        if spec.rescale is not None:
            spec.rescale(floor, factor)


def _gc(name: str) -> None:
    from .models import Floor

    if name and not Floor.objects.filter(plan_file=name).exists():
        (directory() / name).unlink(missing_ok=True)
