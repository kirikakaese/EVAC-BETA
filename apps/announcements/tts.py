# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline speech for announcements (ADR-0022): Piper renders the text once, screens play the file.

Piper and its voices are optional downloads (``pip install piper-tts`` or the image's ``WITH_TTS=1`` build
argument; voices with ``manage.py evac_tts install``). Without them nothing is spoken and the announcement page
says why. Files are named by a hash of voice and text, so the same text is rendered once ("pre-render and
cache") and screens may cache it forever.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

TIMEOUT = 120
KEY = r"[0-9a-f]{64}\.(?:m4a|wav)"


def piper_binary() -> str | None:
    configured = getattr(settings, "EVAC_PIPER_BINARY", "") or "piper"
    return configured if Path(configured).is_file() else shutil.which(configured)


def voices_dir() -> Path:
    configured = getattr(settings, "EVAC_TTS_VOICES_DIR", "")
    return Path(configured) if configured else Path(settings.MEDIA_ROOT) / "tts" / "voices"


def speech_dir() -> Path:
    return Path(settings.MEDIA_ROOT) / "tts"


def voices() -> dict[str, Path]:
    """Installed voices: name -> model path (``<name>.onnx`` with its ``.onnx.json`` next to it)."""
    d = voices_dir()
    if not d.is_dir():
        return {}
    return {p.name[:-5]: p for p in sorted(d.glob("*.onnx")) if p.with_name(p.name + ".json").is_file()}


def voice_info(model: Path) -> dict:
    try:
        data = json.loads(model.with_name(model.name + ".json").read_text())
    except (OSError, ValueError):
        return {}
    lang = data.get("language", {}) if isinstance(data.get("language"), dict) else {}
    return {"language": lang.get("code") or data.get("espeak", {}).get("voice", ""),
            "quality": data.get("audio", {}).get("quality", ""),
            "sample_rate": data.get("audio", {}).get("sample_rate")}


def choose_voice(preferred: str = "") -> tuple[str, Path] | None:
    """The configured voice, else the first English one, else the first installed."""
    found = voices()
    if not found:
        return None
    if preferred in found:
        return preferred, found[preferred]
    english = [n for n in found if n.lower().startswith("en")]
    name = english[0] if english else next(iter(found))
    return name, found[name]


def status(preferred: str = "") -> tuple[bool, str]:
    """(usable, explanation) for the settings and announcement pages."""
    if not piper_binary():
        return False, "Piper is not installed on the server."
    voice = choose_voice(preferred)
    if voice is None:
        return False, f"No voice installed in {voices_dir()}."
    return True, f"Voice {voice[0]}."


def key_for(voice: str, text: str) -> str:
    return hashlib.sha256(f"piper\n{voice}\n{text}".encode()).hexdigest()


class SpeechError(Exception):
    pass


def render(text: str, preferred_voice: str = "") -> str:
    """Speak ``text``; returns the file name (``<key>.m4a`` or ``.wav`` without ffmpeg). Cached by voice+text."""
    binary = piper_binary()
    voice = choose_voice(preferred_voice)
    if binary is None or voice is None:
        raise SpeechError(status(preferred_voice)[1])
    name, model = voice
    key = key_for(name, text)
    out_dir = speech_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("m4a", "wav"):
        if (out_dir / f"{key}.{ext}").is_file():
            return f"{key}.{ext}"
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        try:
            proc = subprocess.run([binary, "--model", str(model), "--output_file", str(wav)], input=text.encode(),
                                  capture_output=True, timeout=TIMEOUT, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SpeechError(f"Piper did not run: {type(exc).__name__}") from None
        if proc.returncode != 0 or not wav.is_file() or wav.stat().st_size < 100:
            tail = proc.stderr.decode(errors="replace").strip().splitlines()[-1:] or [""]
            raise SpeechError(f"Piper failed ({proc.returncode}): {tail[0][:200]}")
        if shutil.which("ffmpeg"):
            m4a = Path(tmp) / "speech.m4a"
            conv = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(wav), "-af",
                                   "loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "1", "-ar", "48000", "-c:a", "aac",
                                   "-b:a", "64k", str(m4a)], capture_output=True, timeout=TIMEOUT, check=False)
            if conv.returncode == 0 and m4a.is_file():
                shutil.move(str(m4a), out_dir / f"{key}.m4a")
                return f"{key}.m4a"
        shutil.move(str(wav), out_dir / f"{key}.wav")
        return f"{key}.wav"


def path_of(file_name: str) -> Path:
    return speech_dir() / Path(file_name).name
