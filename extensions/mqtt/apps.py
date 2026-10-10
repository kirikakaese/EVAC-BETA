# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class MqttConfig(AppConfig):
    name = "extensions.mqtt"
    label = "mqtt"
    verbose_name = "MQTT extension"
