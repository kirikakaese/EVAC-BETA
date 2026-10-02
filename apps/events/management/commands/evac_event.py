# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from apps.events import services
from apps.events.models import Event


class Command(BaseCommand):
    help = "Export or import an event as JSON: evac_event export <slug> [-o file] | import <file> [--slug s]"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["export", "import"])
        parser.add_argument("target", help="event slug (export) or JSON file (import)")
        parser.add_argument("-o", "--output", default="-")
        parser.add_argument("--slug", default="")

    def handle(self, *args, action, target, output, slug, **opts):
        if action == "export":
            event = Event.objects.filter(slug=target).first()
            if event is None:
                raise CommandError(f"no event {target!r}")
            text = json.dumps(services.export_event(event), indent=2, default=str)
            if output == "-":
                sys.stdout.write(text + "\n")
            else:
                with open(output, "w", encoding="utf-8") as fh:
                    fh.write(text)
            return
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
        event, report = services.import_event(data, slug=slug)
        for line in report:
            self.stdout.write(self.style.WARNING(line))
        self.stdout.write(self.style.SUCCESS(f"Imported as /e/{event.slug}/"))
