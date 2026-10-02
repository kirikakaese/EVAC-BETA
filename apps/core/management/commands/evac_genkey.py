# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.management.base import BaseCommand

from apps.core.crypto import generate_key


class Command(BaseCommand):
    help = "Print a new key for EVAC_SECRETS_KEYS (prepend it to rotate, then run evac_rotate_secrets)."

    def handle(self, *args, **opts):
        self.stdout.write(generate_key())
