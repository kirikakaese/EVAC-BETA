# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class ScreensConfig(AppConfig):
    name = "apps.screens"
    label = "screens"
    verbose_name = "Screens"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.core.models import SettingValue

        from . import signals

        post_save.connect(signals.settings_changed, sender=SettingValue, dispatch_uid="screens-settings-saved")
        post_delete.connect(signals.settings_changed, sender=SettingValue, dispatch_uid="screens-settings-deleted")
