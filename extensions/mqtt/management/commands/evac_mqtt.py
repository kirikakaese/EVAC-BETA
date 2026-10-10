# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the MQTT subscriber for hardware bridges (extensions/mqtt). Runs until stopped."

    def handle(self, *args, **opts):  # pragma: no cover - long-running process
        from extensions.mqtt import client

        client.run()
