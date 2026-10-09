# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline speech voices (ADR-0022).

    manage.py evac_tts status
    manage.py evac_tts list
    manage.py evac_tts install <url or path>   # .tar.gz with <voice>.onnx(.json), or the .onnx (its .json next to it)
    manage.py evac_tts say "Doors open in ten minutes" [--voice NAME]
"""
from __future__ import annotations

import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.announcements import tts

# Piper voice files are published at https://huggingface.co/rhasspy/piper-voices (English voices: en_GB, en_US)
DEFAULT_SOURCE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx"
MAX_BYTES = 400 * 1024 * 1024


def _fetch(src: str, dest: Path) -> Path:
    if src.startswith(("https://", "http://")):
        target = dest / Path(src.split("?")[0]).name
        with urllib.request.urlopen(src, timeout=60) as r, open(target, "wb") as out:  # noqa: S310 - admin input
            size = 0
            while chunk := r.read(1 << 20):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise CommandError("download too large")
                out.write(chunk)
        return target
    path = Path(src)
    if not path.is_file():
        raise CommandError(f"no such file: {src}")
    return path


class Command(BaseCommand):
    help = "Install and test voices for spoken announcements (Piper)."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)
        sub.add_parser("status")
        sub.add_parser("list")
        inst = sub.add_parser("install")
        inst.add_argument("source", nargs="?", default=DEFAULT_SOURCE)
        say = sub.add_parser("say")
        say.add_argument("text")
        say.add_argument("--voice", default="")

    def handle(self, *args, action, **opts):
        getattr(self, f"do_{action}")(**opts)

    def do_status(self, **opts):
        ok, why = tts.status()
        self.stdout.write(f"piper: {tts.piper_binary() or 'not found'}")
        self.stdout.write(f"voices: {tts.voices_dir()}")
        self.stdout.write(("ready: " if ok else "not ready: ") + why)

    def do_list(self, **opts):
        found = tts.voices()
        if not found:
            self.stdout.write(f"No voices in {tts.voices_dir()}.")
        for name, path in found.items():
            info = tts.voice_info(path)
            self.stdout.write(f"{name}  {info.get('language', '')}  {info.get('quality', '')}  "
                              f"{path.stat().st_size // 1_000_000} MB")

    def do_install(self, source, **opts):
        target = tts.voices_dir()
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmpd = Path(tmp)
            first = _fetch(source, tmpd)
            models: list[Path] = []
            if first.name.endswith((".tar.gz", ".tgz", ".tar")):
                with tarfile.open(first) as tar:
                    for m in tar.getmembers():
                        name = Path(m.name).name
                        if m.isfile() and name.endswith((".onnx", ".onnx.json")):
                            m.name = name  # flatten, never write outside tmp
                            tar.extract(m, tmpd / "x", filter="data")
                models = sorted((tmpd / "x").glob("*.onnx"))
            elif first.name.endswith(".onnx"):
                # the config (<voice>.onnx.json) sits next to the model: in the same folder or at the same URL
                if not first.with_name(first.name + ".json").is_file():
                    if not source.startswith(("https://", "http://")):
                        raise CommandError(f"{first.name}.json is missing next to the model")
                    _fetch(source.split("?")[0] + ".json", first.parent)
                models = [first]
            else:
                raise CommandError("expected a .tar.gz voice package or a .onnx file")
            installed = []
            for model in models:
                cfg = model.with_name(model.name + ".json")
                if not cfg.is_file():
                    raise CommandError(f"{model.name}: the .onnx.json next to it is missing")
                shutil.copy(model, target / model.name)
                shutil.copy(cfg, target / cfg.name)
                installed.append(model.name[:-5])
        if not installed:
            raise CommandError("no voice found in the package")
        self.stdout.write(self.style.SUCCESS(f"Installed: {', '.join(installed)} in {target}"))

    def do_say(self, text, voice, **opts):
        try:
            name = tts.render(text, voice)
        except tts.SpeechError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(str(tts.path_of(name)))
