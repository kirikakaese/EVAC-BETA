# SPDX-License-Identifier: AGPL-3.0-or-later
"""Asset processing: detection, SVG sanitising, image derivatives (Pillow), video/audio (ffmpeg).

Uploads are accepted by extension **and** content check (Pillow / ffprobe / XML / JSON parse). Derivatives:

* image: ``thumb`` (480 px WebP), ``webp`` and ``avif`` (max ``image_max_px``), EXIF rotation applied and
  metadata (GPS!) stripped; animated GIF/WebP keep their original plus a still thumbnail
* svg: sanitised original (no scripts, event handlers, foreign objects or external references)
* video: ``poster`` (WebP), ``mp4`` (H.264/AAC) and ``webm`` (VP9/Opus), max 1920 px wide
* audio: ``audio`` (AAC, loudness normalised to -16 LUFS)
* pdf, lottie: stored as they are

Without ffmpeg (e.g. a plain dev box) video/audio stay as uploaded and the asset notes why.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as SafeET
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from apps.core.svg import sanitize_svg  # noqa: F401 - used by services (shared with floor plans)

from . import storage

log = logging.getLogger("evac.content")

EXTENSIONS = {
    "jpg": ("image", "image/jpeg"), "jpeg": ("image", "image/jpeg"), "png": ("image", "image/png"),
    "gif": ("image", "image/gif"), "webp": ("image", "image/webp"), "avif": ("image", "image/avif"),
    "svg": ("svg", "image/svg+xml"),
    "mp4": ("video", "video/mp4"), "m4v": ("video", "video/mp4"), "mov": ("video", "video/quicktime"),
    "webm": ("video", "video/webm"), "mkv": ("video", "video/x-matroska"),
    "mp3": ("audio", "audio/mpeg"), "m4a": ("audio", "audio/mp4"), "aac": ("audio", "audio/aac"),
    "wav": ("audio", "audio/wav"), "ogg": ("audio", "audio/ogg"), "opus": ("audio", "audio/ogg"),
    "flac": ("audio", "audio/flac"),
    "pdf": ("pdf", "application/pdf"),
    "json": ("lottie", "application/json"), "lottie": ("lottie", "application/json"),
}
VARIANT_MIME = {"webp": "image/webp", "avif": "image/avif", "mp4": "video/mp4", "webm": "video/webm",
                "m4a": "audio/mp4", "svg": "image/svg+xml"}

Image.MAX_IMAGE_PIXELS = 120_000_000  # decompression-bomb guard (~ 11k x 11k)


class Rejected(ValueError):
    """The upload is not an acceptable file of the claimed type."""


def extension_of(name: str) -> str:
    return Path(name or "").suffix.lower().lstrip(".")


def classify(name: str) -> tuple[str, str, str]:
    ext = extension_of(name)
    if ext not in EXTENSIONS:
        raise Rejected(f"File type .{ext or '?'} is not supported.")
    kind, mime = EXTENSIONS[ext]
    return kind, mime, ext


def has_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


# --------------------------------------------------------------------------- validation on upload

def inspect(kind: str, src: Path) -> dict[str, Any]:
    """Check the content matches the type; return width/height/duration where known."""
    if kind == "image":
        try:
            with Image.open(src) as im:
                im.verify()
            with Image.open(src) as im:
                return {"width": im.width, "height": im.height}
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise Rejected("This is not a valid image.") from exc
    if kind == "svg":
        try:
            root = SafeET.parse(src).getroot()
        except Exception as exc:  # noqa: BLE001 - defusedxml raises several types
            raise Rejected("This is not a valid SVG file.") from exc
        if not root.tag.endswith("svg"):
            raise Rejected("This is not a valid SVG file.")
        return {}
    if kind == "pdf":
        if not src.read_bytes()[:5] == b"%PDF-":
            raise Rejected("This is not a PDF file.")
        return {}
    if kind == "lottie":
        try:
            data = json.loads(src.read_text("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise Rejected("This is not a Lottie JSON file.") from exc
        if not isinstance(data, dict) or "layers" not in data or "v" not in data:
            raise Rejected("This JSON file is not a Lottie animation.")
        return {"width": data.get("w"), "height": data.get("h"),
                "duration": (data.get("op", 0) - data.get("ip", 0)) / (data.get("fr") or 30)}
    if kind in ("video", "audio"):
        if not has_ffmpeg():
            return {}
        info = probe(src)
        streams = info.get("streams", [])
        if kind == "video" and not any(s.get("codec_type") == "video" for s in streams):
            raise Rejected("This file contains no video.")
        if kind == "audio" and not any(s.get("codec_type") == "audio" for s in streams):
            raise Rejected("This file contains no audio.")
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        duration = info.get("format", {}).get("duration")
        return {"width": video.get("width"), "height": video.get("height"),
                "duration": float(duration) if duration else None}
    return {}


def probe(src: Path) -> dict[str, Any]:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                              str(src)], capture_output=True, check=True, timeout=60)
        return json.loads(out.stdout or b"{}")
    except (subprocess.SubprocessError, ValueError) as exc:
        raise Rejected("The media file could not be read.") from exc


# --------------------------------------------------------------------------- derivatives

def _save(im: Image.Image, sha: str, name: str, fmt: str, **kw) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(suffix=f".{fmt.lower()}", delete=False) as tmp:
        im.save(tmp, fmt, **kw)
    dst = storage.store(sha, name, Path(tmp.name), move=True)
    return {"file": name, "mime": VARIANT_MIME[name.rsplit(".", 1)[1]], "size": dst.stat().st_size}


def image_variants(sha: str, src: Path, *, max_px: int, avif: bool) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with Image.open(src) as im:
        animated = getattr(im, "is_animated", False)
        frame = next(ImageSequence.Iterator(im)).copy() if animated else im.copy()
    frame = ImageOps.exif_transpose(frame)
    if frame.mode not in ("RGB", "RGBA"):
        frame = frame.convert("RGBA" if "A" in frame.getbands() or frame.mode == "P" else "RGB")
    thumb = frame.copy()
    thumb.thumbnail((480, 480))
    out["thumb"] = _save(thumb, sha, "thumb.webp", "WEBP", quality=80, method=4)
    if not animated:
        full = frame.copy()
        full.thumbnail((max_px, max_px))
        out["webp"] = _save(full, sha, "image.webp", "WEBP", quality=85, method=4)
        if avif:
            try:
                out["avif"] = _save(full, sha, "image.avif", "AVIF", quality=60)
            except (OSError, KeyError, ValueError) as exc:  # Pillow without AVIF support
                log.info("AVIF encoding unavailable: %s", exc)
    return out


def _ffmpeg(args: list[str], timeout: int = 3600) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, capture_output=True,
                   timeout=timeout)


def _variant_file(sha: str, name: str) -> dict[str, Any]:
    p = storage.path(sha, name)
    return {"file": name, "mime": VARIANT_MIME[name.rsplit(".", 1)[1]], "size": p.stat().st_size}


def video_variants(sha: str, src: Path, *, duration: float | None, webm: bool) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    storage.directory(sha).mkdir(parents=True, exist_ok=True)
    at = "1" if (duration or 0) > 2 else "0"
    scale = "scale='min(1920,iw)':-2"
    _ffmpeg(["-ss", at, "-i", str(src), "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-c:v", "libwebp",
             str(storage.path(sha, "poster.webp"))], timeout=120)
    out["poster"] = _variant_file(sha, "poster.webp")
    thumb = storage.path(sha, "thumb.webp")
    with Image.open(storage.path(sha, "poster.webp")) as im:
        im.thumbnail((480, 480))
        im.save(thumb, "WEBP", quality=80)
    out["thumb"] = _variant_file(sha, "thumb.webp")
    _ffmpeg(["-i", str(src), "-vf", scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt",
             "yuv420p", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", str(storage.path(sha, "video.mp4"))])
    out["mp4"] = _variant_file(sha, "video.mp4")
    if webm:
        _ffmpeg(["-i", str(src), "-vf", scale, "-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0", "-row-mt", "1",
                 "-deadline", "realtime", "-cpu-used", "8", "-c:a", "libopus", "-b:a", "96k",
                 str(storage.path(sha, "video.webm"))])
        out["webm"] = _variant_file(sha, "video.webm")
    return out


def audio_variants(sha: str, src: Path) -> dict[str, dict[str, Any]]:
    storage.directory(sha).mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-i", str(src), "-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k",
             str(storage.path(sha, "audio.m4a"))])
    return {"audio": _variant_file(sha, "audio.m4a")}
