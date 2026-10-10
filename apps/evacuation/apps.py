# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class EvacuationConfig(AppConfig):
    name = "apps.evacuation"
    label = "evacuation"
    verbose_name = "Evacuation"

    def ready(self) -> None:
        from django.db.models.signals import post_delete, post_save

        from apps.core.models import SettingValue

        from . import signals

        post_save.connect(signals.settings_changed, sender=SettingValue, dispatch_uid="evac-settings-saved")
        post_delete.connect(signals.settings_changed, sender=SettingValue, dispatch_uid="evac-settings-deleted")
