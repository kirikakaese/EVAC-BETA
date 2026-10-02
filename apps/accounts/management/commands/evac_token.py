# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import ServiceToken, User
from apps.events.models import Event


class Command(BaseCommand):
    help = "Create a service token for a user: evac_token <email> <name> [--scopes events:read ...] [--event slug]"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("name")
        parser.add_argument("--scopes", nargs="*", default=[])
        parser.add_argument("--event", default="")

    def handle(self, *args, email, name, scopes, event, **opts):
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"no user {email}")
        ev = Event.objects.filter(slug=event).first() if event else None
        if event and ev is None:
            raise CommandError(f"no event {event}")
        _tok, raw = ServiceToken.issue(name=name, owner=user, event=ev, scopes=scopes)
        self.stdout.write(raw)
