# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "apps.api"
    label = "api"
    verbose_name = "REST API"

    def ready(self):
        from . import schema  # noqa: F401 - registers the OpenAPI auth extension
