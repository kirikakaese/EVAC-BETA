# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class ContentConfig(AppConfig):
    name = "apps.content"
    label = "content"
    verbose_name = "Screen content"
    default_auto_field = "django.db.models.BigAutoField"
