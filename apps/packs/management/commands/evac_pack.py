# SPDX-License-Identifier: AGPL-3.0-or-later
"""``manage.py evac_pack``: export, verify and import ``.evacpack`` files, show the instance key (ADR-0024).

  evac_pack key
  evac_pack verify <file>
  evac_pack export <event> <file> --layouts <id,...> --themes ... --playlists ... --widgets ... [--name N] [--unsigned]
  evac_pack import <event> <file> [--yes]
"""
from __future__ import annotations

from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.events.models import Event
from apps.packs import engine, packfile, services


class Command(BaseCommand):
    help = "Export, verify and import .evacpack files"

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="cmd", required=True)
        sub.add_parser("key", help="show this server's public key")
        v = sub.add_parser("verify", help="check a pack (structure, hashes, signature)")
        v.add_argument("file")
        e = sub.add_parser("export", help="export objects of an event")
        e.add_argument("event")
        e.add_argument("file")
        e.add_argument("--name", default="")
        e.add_argument("--unsigned", action="store_true")
        for spec in engine.sections():
            e.add_argument(f"--{spec.key}", default="", help=f"comma-separated ids ({spec.title})")
        i = sub.add_parser("import", help="import a pack into an event")
        i.add_argument("event")
        i.add_argument("file")
        i.add_argument("--yes", action="store_true", help="import unsigned packs or packs from unknown keys")

    def _event(self, slug: str) -> Event:
        event = Event.objects.filter(slug=slug).first()
        if event is None:
            raise CommandError(f"Unknown event {slug}")
        return event

    def handle(self, *args, cmd, **opts):
        if cmd == "key":
            key = services.own_public_key()
            self.stdout.write(f"{key}\n{packfile.fingerprint(key)}")
        elif cmd == "verify":
            try:
                pack = packfile.read(Path(opts["file"]), max_bytes=services.max_bytes())
            except (packfile.PackError, OSError) as exc:
                raise CommandError(str(exc)) from None
            self.stdout.write(f"{pack.manifest.get('name')}: valid, {services.trust_of(pack)}"
                              + (f" ({pack.signer}, {packfile.fingerprint(pack.public_key)})" if pack.signed else ""))
            for key, items in pack.sections.items():
                self.stdout.write(f"  {key}: {len(items)}")
        elif cmd == "export":
            event = self._event(opts["event"])
            selection = {s.key: {x for x in (opts.get(s.key) or "").split(",") if x} for s in engine.sections()}
            try:
                with open(opts["file"], "wb") as out:
                    services.export(event, selection, name=opts["name"] or event.name, actor=None,
                                    sign=not opts["unsigned"], out=out)
            except ValidationError as exc:
                Path(opts["file"]).unlink(missing_ok=True)
                raise CommandError("; ".join(exc.messages)) from None
            self.stdout.write(f"Wrote {opts['file']}")
        elif cmd == "import":
            event = self._event(opts["event"])
            try:
                with open(opts["file"], "rb") as fh:
                    pi = services.stage_upload(event, File(fh, name=Path(opts["file"]).name), actor=None)
                if pi.status != pi.Status.READY:
                    raise CommandError(pi.error)
                result = services.apply(pi, actor=None, confirmed=opts["yes"])
            except ValidationError as exc:
                raise CommandError("; ".join(exc.messages)) from None
            for key, names in result["created"].items():
                self.stdout.write(f"{key}: {', '.join(names)}")
            for w in result["warnings"]:
                self.stdout.write(self.style.WARNING(w))
