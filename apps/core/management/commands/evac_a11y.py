# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from apps.core.a11y import audit_url, smoke_urls


class Command(BaseCommand):
    help = "Run the accessibility linter against pages of the (seeded) database as an instance admin."

    def add_arguments(self, parser):
        parser.add_argument("--url", action="append", default=[])
        parser.add_argument("--event", default="demo")
        parser.add_argument("--as", dest="email", default="admin@evac.local")

    def handle(self, *args, url, event, email, **opts):
        user = get_user_model().objects.filter(email=email).first()
        if user is None:
            raise CommandError(f"no user {email} (run evac_seed_demo)")
        client = Client(HTTP_HOST="localhost")
        client.force_login(user)
        total = 0
        for u in url or smoke_urls(event)["admin"]:
            findings = audit_url(client, u)
            if findings is None:
                self.stdout.write(f"SKIP {u}")
                continue
            total += len(findings)
            for f in findings:
                self.stdout.write(f"{u}: {f}")
        if total:
            raise CommandError(f"{total} finding(s)")
        self.stdout.write(self.style.SUCCESS("No accessibility findings."))
