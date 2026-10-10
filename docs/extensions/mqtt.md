# MQTT

Hardware bridges ([bridge/README.md](../../bridge/README.md)) can talk MQTT instead of HTTPS, through a broker you run
(for example Mosquitto on the venue node). EVAC does not ship a broker.

## Set up

1. *Settings → Extensions → MQTT*: broker host, port (8883 with TLS), username, password (stored encrypted) and the
   topic prefix (default `evac`). *Test connection* connects once.
2. Run the subscriber process: `docker compose --profile mqtt up -d` (Docker), `systemctl enable --now evac-mqtt`
   (systemd) or `python manage.py evac_mqtt`. It idles until the extension is configured and reconnects after
   changes.
3. On the bridge set `transport = "mqtt"` and the `[mqtt]` block.

## Topics

| Topic | Direction | Body |
|---|---|---|
| `<prefix>/bridge/<id>/heartbeat` | bridge → EVAC | `{"token", "inputs": {"in1": "rest"}, "info": {...}}` |
| `<prefix>/bridge/<id>/input` | bridge → EVAC | `{"token", "input": "in1", "state": "active", "id": "<unique>"}` |
| `<prefix>/bridge/<id>/config` | EVAC → bridge | the bridge configuration (answer to a heartbeat) |
| `<prefix>/bridge/<id>/result` | EVAC → bridge | `{"id", "result"}` |

| `<prefix>/crowd/<event slug>/<sensor key>` | sensor → EVAC | occupancy: `{"in": 3, "out": 1}`, `{"delta": 2}`, `{"value": 140}` or a bare number (the occupancy); optional `"id"` makes a repeat harmless (ADR-0040) |

Modules can add topics with `r.mqtt_topic(...)`. The extension subscribes to them as well.

`<id>` is free (the reference bridge uses the first 12 characters of its token). Every message carries the bridge
token: the broker's own access control is a second layer, not the only one. Restrict the bridge accounts to their
topics in the broker's ACL.
