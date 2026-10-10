# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.events.models import Event


class Command(BaseCommand):
    help = ("The event's alarm signing key (ADR-0034): evac_alarm_key <event> show | rotate | export "
            "[--purpose 'bridge hall A']. Export prints the private key (audit-logged); handle it like a password.")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("event")
        parser.add_argument("action", choices=["show", "rotate", "export"])
        parser.add_argument("--purpose", default="")

    def handle(self, *args: Any, event: str, action: str, purpose: str, **opts: Any) -> None:
        from apps.evacuation import alarmkey, feed

        ev = Event.objects.filter(slug=event).first()
        if ev is None:
            raise CommandError(f"no event {event}")
        if action == "rotate":
            alarmkey.rotate(ev)
            feed.push(ev)
        if action == "export":
            self.stdout.write(alarmkey.export_private(ev, purpose=purpose or "management command"))
            return
        for i, key in enumerate(alarmkey.public_keys(ev)):
            self.stdout.write(f"{'current ' if i == 0 else 'previous'} {key}")
