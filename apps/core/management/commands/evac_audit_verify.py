# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.management.base import BaseCommand, CommandError

from apps.core.audit import verify_chain


class Command(BaseCommand):
    help = "Verify the audit log hash chain. Exit code 1 if tampering is detected."

    def handle(self, *args, **opts):
        result = verify_chain()
        if not result.ok:
            raise CommandError(f"Audit chain BROKEN at row {result.first_bad_id}: {result.reason} "
                               f"({result.checked} rows checked)")
        self.stdout.write(self.style.SUCCESS(f"Audit chain OK ({result.checked} rows)."))
