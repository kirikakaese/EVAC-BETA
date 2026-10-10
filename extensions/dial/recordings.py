# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announce by phone (brief §9, roadmap 4.2): an orga calls DIAL and records a message; DIAL posts
``announcement.recorded``; this outbox job imports the audio, transcribes it (optional, offline) and creates an
announcement that waits in the approval queue, or is published at once when the calling extension is on the link's
allow-list.

DIAL links the file as ``audio`` (its media name). EVAC looks it up in DIAL's IVR API (``ivr/announcements/``,
absolute URL) and downloads it from the DIAL host only; when DIAL does not serve its media the announcement is still
created, without audio, and the recording row says why.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from django.utils.translation import gettext as _

from . import link, whisper
from .client import Client, DialError, Rejected
from .models import Recording

log = logging.getLogger("evac.dial")


def audio_url(client: Client, rec: Recording) -> str:
    """The absolute URL of the recording on the DIAL server."""
    try:
        items = client.results("ivr/announcements/", event=client.event)
    except Rejected:
        items = []
    for item in items:
        if isinstance(item, dict) and str(item.get("extension_number")) == rec.extension and item.get("audio"):
            url = str(item["audio"])
            if rec.audio and not url.endswith(rec.audio):
                continue
            return url
    return f"{client.base}/media/{rec.audio.lstrip('/')}"


def on_base(client: Client, url: str) -> str:
    """DIAL renders absolute URLs with whatever host it was asked by (or an internal one behind a proxy): fetch the
    path from the configured DIAL URL, so the token never goes anywhere else."""
    path = urlsplit(url).path
    if not path.startswith("/") or ".." in path.split("/"):
        raise Rejected("Unexpected recording path.", 0)
    return f"{client.base}{path}"


def store(data: bytes) -> str:
    """Save as announcement speech (``<sha256>.m4a``, normalised with ffmpeg when available, else ``.wav``)."""
    from apps.announcements import tts

    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise Rejected("The recording is not a WAV file.", 0)
    key = hashlib.sha256(data).hexdigest()
    out = tts.speech_dir()
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("m4a", "wav"):
        if (out / f"{key}.{ext}").is_file():
            return f"{key}.{ext}"
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "rec.wav"
        wav.write_bytes(data)
        if shutil.which("ffmpeg"):
            m4a = Path(tmp) / "rec.m4a"
            conv = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav), "-af",
                                   "loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "1", "-ar", "48000", "-c:a", "aac",
                                   "-b:a", "64k", str(m4a)], capture_output=True, timeout=120, check=False)
            if conv.returncode == 0 and m4a.is_file():
                shutil.move(str(m4a), out / f"{key}.m4a")
                return f"{key}.m4a"
        shutil.move(str(wav), out / f"{key}.wav")
        return f"{key}.wav"


def _level(event: Any, wanted: str) -> Any:
    from apps.announcements import services as ann
    from apps.announcements.models import Level

    ann.ensure_defaults(event)
    levels = Level.objects.filter(event=event, emergency=False)
    return levels.filter(key=wanted).first() or levels.filter(key="info").first() or levels.order_by("rank").first()


def make_announcement(config: Any, rec: Recording) -> Any:
    from apps.announcements import services as ann_services
    from apps.announcements.models import Announcement

    s = link.settings_of(config)
    level = _level(rec.event, str(s.get("recording_level") or "info"))
    if level is None:
        raise Rejected("No announcement level for phone recordings.", 0)
    first = rec.transcript.split(". ")[0].strip().rstrip(".") if rec.transcript else ""
    title = (first[:117] + "…") if len(first) > 120 else first
    title = title or _("Announcement by phone (extension %(e)s)") % {"e": rec.extension}
    body = rec.transcript or _("Recorded by phone from DIAL extension %(e)s (%(d)s s). %(why)s") % {
        "e": rec.extension, "d": rec.duration, "why": rec.detail or ""}
    channels = [c for c in (level.default_channels or []) if c in ann_services.available_channels(rec.event)]
    if not channels:
        channels = ["screens"] if "screens" in ann_services.available_channels(rec.event) else []
    a = Announcement(event=rec.event, level=level, title=title[:200], body=body.strip(), channels=channels,
                     speech_recorded=bool(rec.speech_file))
    if rec.speech_file:
        a.speech_file, a.speech_status = rec.speech_file, Announcement.Speech.READY
    allowed = link.csv(s.get("auto_publish_extensions"))
    return ann_services.submit_external(a, source=f"DIAL extension {rec.extension}",
                                        publish_now=rec.extension in allowed)


def handle_job(job: Any) -> None:
    from apps.core import modules
    from apps.extensions import services as ext

    rec = Recording.objects.select_related("config", "event").filter(pk=job.payload["recording"]).first()
    if rec is None or rec.status == Recording.Status.IMPORTED:
        job.result = {"skipped": "gone or done"}
        return
    config = rec.config
    if not modules.is_enabled("announcements", rec.event):
        rec.status, rec.detail = Recording.Status.FAILED, _("The announcements module is off.")
        rec.save(update_fields=["status", "detail"])
        job.result = {"failed": rec.detail}
        return
    client = Client.for_config(config)
    notes = []
    if rec.audio and not rec.speech_file:
        try:
            rec.speech_file = store(client.download(on_base(client, audio_url(client, rec))))
        except Rejected as exc:
            notes.append(_("The audio could not be fetched from DIAL (%(e)s).") % {"e": exc})
        rec.save(update_fields=["speech_file"])  # a Temporary error propagates: the outbox retries
    elif not rec.audio:
        notes.append(_("DIAL kept the recording on the PBX only."))
    if rec.speech_file and link.settings_of(config).get("transcribe") and not rec.transcript:
        from apps.announcements import tts

        try:
            rec.transcript = whisper.transcribe(tts.path_of(rec.speech_file))[:4000]
        except whisper.TranscriptionError as exc:
            notes.append(_("No transcript: %(e)s") % {"e": exc})
    rec.detail = " ".join(notes)[:300]
    try:
        rec.announcement = make_announcement(config, rec)
    except (DialError, ValueError) as exc:
        rec.status, rec.detail = Recording.Status.FAILED, str(exc)[:300]
        rec.save(update_fields=["status", "detail", "transcript"])
        ext.write_log(config, "error", f"Phone recording from {rec.extension}: {exc}")
        job.result = {"failed": rec.detail}
        return
    rec.status = Recording.Status.IMPORTED
    rec.save(update_fields=["status", "detail", "transcript", "announcement"])
    ext.write_log(config, "info", f"Phone recording from extension {rec.extension} -> announcement "
                                  f"“{rec.announcement.title}” ({rec.announcement.get_status_display()})")
    job.result = {"announcement": str(rec.announcement.pk), "status": rec.announcement.status}
