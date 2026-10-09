# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import AppConfig


class NotifyConfig(AppConfig):
    name = "extensions.notify"
    label = "notify"
    verbose_name = "Announcement channels (e-mail, ntfy, Matrix, Telegram, Mastodon)"
