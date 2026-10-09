# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class AnnouncementsConfig(AppConfig):
    name = "apps.announcements"
    label = "announcements"
    verbose_name = "Announcements"
    default_auto_field = "django.db.models.BigAutoField"
