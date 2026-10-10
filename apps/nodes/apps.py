# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class NodesConfig(AppConfig):
    name = "apps.nodes"
    label = "nodes"
    verbose_name = "Venue nodes"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import recorder

        recorder.connect()
