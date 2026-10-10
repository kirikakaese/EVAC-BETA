# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.events.models import Event


class Command(BaseCommand):
    help = ("Ask the event's screens to run the evacuation self-test (roadmap 3.9), or with --report print the "
            "readiness of every screen: evac_selftest <event> [--visible] [--report]. Exits 1 when a screen is not "
            "ready (for monitoring).")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("event")
        parser.add_argument("--visible", action="store_true", help="also show a test frame for 5 seconds")
        parser.add_argument("--report", action="store_true", help="print readiness instead of sending a test")

    def handle(self, *args: Any, event: str, visible: bool, report: bool, **opts: Any) -> None:
        from apps.evacuation import acks, readiness

        ev = Event.objects.filter(slug=event).first()
        if ev is None:
            raise CommandError(f"no event {event}")
        if not report:
            if visible and acks.alarm_since(ev) is not None:
                raise CommandError("no visible self-test during an alarm")
            n = readiness.run_selftest(ev, visible=visible)
            self.stdout.write(f"self-test sent to {n} screens")
            return
        rows = readiness.screens(ev)
        for r in rows:
            mark = "excluded" if r.role == "excluded" else "ready" if r.ready else "PROBLEM"
            notes = "; ".join(r.problems + r.warnings)
            self.stdout.write(f"{mark:8} {r.screen.name}" + (f"  ({notes})" if notes else ""))
        s = readiness.summary(rows)
        self.stdout.write(f"{s['ready']} of {s['total']} ready")
        if s["problems"]:
            raise SystemExit(1)
