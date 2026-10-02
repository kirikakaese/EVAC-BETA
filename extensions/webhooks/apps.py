# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class WebhooksConfig(AppConfig):
    name = "extensions.webhooks"
    label = "webhooks"
    verbose_name = "Generic webhooks extension"
