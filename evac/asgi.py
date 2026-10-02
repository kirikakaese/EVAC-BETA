# SPDX-License-Identifier: AGPL-3.0-or-later
"""ASGI entry point: HTTP (incl. SSE) via Django, WebSockets via Channels.

The ``channels`` compose service runs this with Daphne. WebSocket routes are collected from every
plugin (``apps.core.registry.registry.websocket_routes``), so modules add their consumers without
touching this file.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evac.settings.prod")
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.core.realtime.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns()))),
    }
)
