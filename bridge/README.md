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

The bridge keeps the changes and retries with backoff (1 s up to 30 s). Issuing signed alarm messages straight to
the screens when no node is reachable (ADR-0003) needs the event's alarm key and is part of the fail-safe design
([docs/EVACUATION.md](../docs/EVACUATION.md)).
