# EVAC hardware bridge

Reference software that connects **dry contacts** (fire alarm panel relays), **buttons** and **key switches** to
EVAC ([ADR-0032](../docs/adr/0032-hardware-bridge.md)). It is a reference implementation, **not a certified
product**: EVAC supplements the venue's legally required fire alarm and voice alarm systems and never replaces
them. Connect only to potential-free relay outputs that the panel's installer provides for third-party systems.

## How it behaves

- Every input change is debounced (200 ms) and sent with a unique id. It is kept in a queue on disk and retried
  until EVAC confirms it, so outages and restarts lose nothing and a retry never raises a second alarm.
- `active` raises the input's stage through the *Hardware bridge* source. By default this **arms** the alarm: the
  control room confirms, or it executes by itself after the escalation time (Triggers & drills).
- `rest` (the panel was reset) **does not end the alarm**: the control room is told "contact restored". Only a
  person gives the all clear.
- `fault` (broken wire, short circuit on a supervised loop) and a missing heartbeat (30 s) only **alert** the
  control room; no public alarm.
- A heartbeat every 10 seconds carries all input states, so a change EVAC missed is caught up.

## Raspberry Pi

1. In EVAC: *Evacuation → Triggers & drills → Hardware bridges → Add a bridge*. Copy the token (shown once) and
   configure the inputs, e.g. `in1; Fire panel relay 3; evacuate; Zone North`.
2. On the Pi (Raspberry Pi OS): `sudo apt install python3-gpiozero`, copy `evac_bridge.py` to `/opt/evac-bridge/`,
   `bridge.example.toml` to `/etc/evac-bridge.toml` (mode 600) and fill in URL, token and pins.
3. `sudo useradd -r -G gpio evac-bridge`, install `evac-bridge.service`, `sudo systemctl enable --now evac-bridge`.
4. Test without wiring: `python3 evac_bridge.py --config ... --simulate`, then type `in1 active`.

Wiring: the default is a normally open contact between the GPIO pin and ground (internal pull-up), so a closed
contact is `active`. Digital pins cannot tell a broken wire from an open contact: for **supervised lines** use the
ESP32 below or an ADC hat with end-of-line resistors (`kind = "loop"`, bands `rest_band` / `active_band`).

## ESP32

`esp32/evac_bridge/evac_bridge.ino` (Arduino ESP32 core) reads supervised loops on ADC1 pins: with an end-of-line
resistor the idle loop reads about half the supply (`rest`), the closed contact adds a parallel resistor
(`active`), an open wire reads near the supply and a short near zero (`fault`). Set Wi-Fi, URL, token, the CA
certificate and the bands in the CONFIG block. The on-board LED shows the link (steady: EVAC reachable).

## MQTT

Set `transport = "mqtt"` and the `[mqtt]` block (needs `pip install paho-mqtt` on the Pi and the MQTT extension
in EVAC, see [docs/extensions/mqtt.md](../docs/extensions/mqtt.md)).

## When EVAC is unreachable

The bridge keeps the changes and retries with backoff (1 s up to 30 s).

With a `[fallback]` section (see `bridge.example.toml`, ADR-0034) the Raspberry Pi bridge also stands in for the
server towards the screens:

- It keeps the signed alarm state from every heartbeat (on disk) and serves it at `/evac/<event>/state` on
  `listen_port`. Add its URL to *Settings → Evacuation → Fallback origins*. Players on an HTTPS page can only
  reach an HTTPS origin: give the bridge a certificate the kiosks trust (`cert_file`, `key_file`).
- With the event's alarm key (*Evacuation → Readiness → Export private key*, or `manage.py evac_alarm_key <event>
  export`) it signs an alarm itself when an input fires and EVAC cannot be reached. It follows the input's policy:
  *execute* at once, *arm* after its escalation time, *notify* never. It never signs an all clear. When EVAC is
  back, the change is delivered with the sequence number the bridge used; EVAC adopts the alarm and alerts the
  control room.
- Keep the configuration file `chmod 600`, or pass the key as `EVAC_BRIDGE_ALARM_KEY`. If a bridge is lost,
  rotate the alarm key.

The ESP32 sketch only reports; it does not serve or sign.
