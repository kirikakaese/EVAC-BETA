# SPDX-License-Identifier: AGPL-3.0-or-later
"""MQTT transport for hardware bridges (ADR-0032). Off until configured under Settings -> Extensions; you run the
broker. The ``mqtt`` process (``manage.py evac_mqtt``, entrypoint role ``mqtt``) subscribes to
``<prefix>/bridge/+/heartbeat`` and ``<prefix>/bridge/+/input`` and answers heartbeats on ``.../config``."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.core.plugins import ExtensionSpec, PluginManifest
from apps.core.registry import Registry

manifest = PluginManifest(key="mqtt", name="MQTT", version="1.0.0", kind="extension",
                          description="MQTT transport for evacuation hardware bridges.")


def register(r: Registry) -> None:
    from . import client

    r.extension(ExtensionSpec(
        key="mqtt", name="MQTT", version="1.0.0", scope="instance", icon="⇄", docs="extensions/mqtt",
        description=str(_("Hardware bridges can talk MQTT instead of HTTPS, through a broker you run (e.g. "
                          "Mosquitto). Needs the mqtt process (entrypoint role “mqtt”).")),
        settings_schema={"type": "object", "required": ["host"], "properties": {
            "host": {"type": "string", "title": "Broker host", "maxLength": 200},
            "port": {"type": "integer", "title": "Port", "default": 8883, "minimum": 1, "maximum": 65535},
            "tls": {"type": "boolean", "title": "Use TLS", "default": True},
            "username": {"type": "string", "title": "Username", "maxLength": 100},
            "topic_prefix": {"type": "string", "title": "Topic prefix", "default": "evac", "maxLength": 60,
                             "pattern": "^[A-Za-z0-9_/-]+$"},
        }},
        secret_fields=(("password", str(_("Password"))),),
        test_connection=client.test_connection))
