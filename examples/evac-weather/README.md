# evac-weather — example EVAC plugin

The example of the [EVAC plugin SDK](../../docs/PLUGIN_SDK.md). Installed with pip, it adds to EVAC — without any
change to EVAC itself:

| What | Where |
|---|---|
| data source `weather.current` | the latest weather observation of the event (`services.current`) |
| screen widget `weather.current` | the custom element `<evac-x-weather>` (`static/evac_weather/weather.js`), in the layout editor under **Plugin widget** with a generated settings form (heading, °C/°F, wind) |
| extension *Weather* | Settings → Extensions → Weather: place name, optional Open-Meteo location; its page **Open** lists readings and takes new ones by hand (works offline) |
| model + migration | `Observation` (every change audited as `weather.recorded`) |
| Celery task | `evac_weather.tasks.fetch`: Open-Meteo through EVAC's safe fetcher, queued when the latest reading is older than the refresh interval, at most once a minute |

## Install

```sh
.venv/bin/pip install ./examples/evac-weather     # registers the entry point "evac.plugins: weather"
.venv/bin/python manage.py migrate
# restart EVAC (web, websocket and Celery workers)
```

`EVAC_DISABLED_PLUGINS=evac_weather` switches it off again without uninstalling.

## Use

1. Settings → Extensions → **Weather**: enable it for the event, give a place name; tick *Fetch from Open-Meteo*
   and set latitude/longitude if the server has internet.
2. **Open** the extension page and enter a reading (or *Fetch now*).
3. Content → Layouts → edit a layout → **Plugin widget** → *Weather*; publish. Screens show the reading and keep
   the last one while offline.

## Tests

From the EVAC checkout, after installing:

```sh
.venv/bin/python -m pytest examples/evac-weather/tests
```

Licence: AGPL-3.0-or-later.
