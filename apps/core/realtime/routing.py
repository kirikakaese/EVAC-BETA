# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path


def websocket_urlpatterns():
    from apps.core.registry import registry

    from .consumers import EventStreamConsumer

    return [path("ws/e/<slug:slug>/", EventStreamConsumer.as_asgi()), *registry.ensure_loaded().websocket_routes]
