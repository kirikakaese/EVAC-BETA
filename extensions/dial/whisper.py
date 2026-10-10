# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional offline transcription of phone recordings with whisper.cpp (English model).

Nothing is installed by default: put the ``whisper-cli`` binary on the PATH (or set ``EVAC_WHISPER_BINARY``) and an
English ggml model at ``EVAC_WHISPER_MODEL`` (default ``<MEDIA_ROOT>/whisper/ggml-base.en.bin``). Without them the
announcement is created without a transcript and says so. Runs in the outbox worker, never in a request.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

TIMEOUT = 300


class TranscriptionError(Exception):
    pass


def binary() -> str | None:
    configured = getattr(settings, "EVAC_WHISPER_BINARY", "") or "whisper-cli"
    return configured if Path(configured).is_file() else shutil.which(configured)


def model() -> Path:
    configured = getattr(settings, "EVAC_WHISPER_MODEL", "")
    return Path(configured) if configured else Path(settings.MEDIA_ROOT) / "whisper" / "ggml-base.en.bin"


def status() -> tuple[bool, str]:
    if not binary():
        return False, "whisper.cpp (whisper-cli) is not installed on the server."
    if not model().is_file():
        return False, f"No Whisper model at {model()}."
    if not shutil.which("ffmpeg"):
        return False, "ffmpeg is needed to prepare the audio."
    return True, f"Whisper model {model().name}."


def transcribe(audio: Path) -> str:
    usable, why = status()
    if not usable:
        raise TranscriptionError(why)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "in.wav"
        conv = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(audio), "-ac", "1",
                               "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], capture_output=True, timeout=TIMEOUT,
                              check=False)
        if conv.returncode != 0:
            raise TranscriptionError("ffmpeg could not read the recording.")
        out = Path(tmp) / "out"
        try:
            proc = subprocess.run([str(binary()), "-m", str(model()), "-f", str(wav), "-l", "en", "-nt", "-otxt",
                                   "-of", str(out)], capture_output=True, timeout=TIMEOUT, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TranscriptionError(f"Whisper did not run: {type(exc).__name__}") from None
        txt = out.with_suffix(".txt")
        if proc.returncode != 0 or not txt.is_file():
            raise TranscriptionError(f"Whisper failed ({proc.returncode}).")
        return " ".join(txt.read_text(errors="replace").split()).strip()
