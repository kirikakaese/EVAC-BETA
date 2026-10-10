# ADR-0032: Hardware bridge and MQTT transport

- Status: Accepted
- Date: 2026-10-10

## Context

Roadmap 3.6 and brief §8.3: a reference bridge for Raspberry Pi GPIO and an ESP32 (dry contacts from a fire alarm
panel relay, mushroom buttons, key switches), talking to the node over authenticated MQTT or HTTPS and supervising
its line, so a dead bridge raises an alert. ADR-0003 set its default policy to *arm* and says it never issues the
all clear. The project owner decided on 2026-10-10:

1. A contact returning to rest (panel reset) only **notifies** the control room; the alarm stays.
2. A missed heartbeat or a wiring fault raises a **fault alert only**: control room and bridge page, no public
   alarm. Heartbeat every 10 s, offline after 30 s.
3. When EVAC is unreachable the bridge **buffers and retries**; issuing signed state straight to screens comes
   with the fail-safe (3.9).
4. MQTT ships as an **optional extension**; the operator runs the broker.

## Decision

- **`Bridge`** per event: name, token (`evacb_…`, only its SHA-256 stored, rotatable), inputs (`key`, label,
  stage, optional zone), last reported input states, online flag, last heartbeat, transport. Managed on
  *Triggers & drills → Hardware bridges* (`evacuation.manage`); every change audit-logged.
- **Protocol** (HTTPS `POST /bridge/v1/heartbeat` and `/bridge/v1/input`, `Authorization: Bearer evacb_…`; the
  same JSON over MQTT with the token in the body):
  - `input` `{input, state: active|rest|fault, id}`. The id is the idempotency key, so a retry never raises a
    second alarm.
  - `heartbeat` `{inputs: {key: state}, info}`. It answers with the bridge configuration, and states that
    differ from the last report are handled as changes, so a lost change is caught up.
- **Handling** (`apps/evacuation/bridges.py`):
  - `active` → `triggers.trigger(source="bridge")` with the input's stage and zone (default *arm*, ADR-0031).
  - `rest` after `active` → "contact restored" alert, alarm unchanged.
  - `fault` → "input fault" alert once per fault.
  - Celery beat (`process_due`, 5 s) marks bridges without a heartbeat for 30 s offline and alerts, and a
    "back online" alert follows.
- **Endpoints** are exempt from the early-access gate (own token) and rate-limited (600/min per IP).
- **MQTT** (`extensions/mqtt`, instance-wide, off until configured):
  - Topics `<prefix>/bridge/<id>/heartbeat|input`, answers on `…/config` and `…/result`.
  - The subscriber process `manage.py evac_mqtt` runs as the entrypoint role `mqtt`, the compose profile
    `mqtt` and the systemd unit `evac-mqtt`.
  - `paho-mqtt` (pure Python, ~200 kB) is a regular dependency.
  - Message handling (`client.handle`) is transport-independent and tested without a broker.
- **Reference software** in `bridge/`:
  - `evac_bridge.py` for the Pi: standard library only, plus `gpiozero` for the pins and optionally `paho-mqtt`.
    It debounces inputs, keeps a persistent queue, retries with backoff, sends heartbeats and has a
    `--simulate` mode. There are unit tests for classification, debouncing, the queue and sending.
  - The ESP32 sketch supervises loops with end-of-line resistors on the ADC (rest / active / open / short).

## Consequences

- Pi digital inputs are unsupervised apart from the heartbeat; supervised lines need the ESP32 or an ADC.
- When no node is reachable the bridge can only queue; issuing signed alarm messages to screens directly
  (ADR-0003) is added with the alarm key in 3.9.
- DIAL (phase 4) and other systems use the API trigger; bridges are for wired contacts.
