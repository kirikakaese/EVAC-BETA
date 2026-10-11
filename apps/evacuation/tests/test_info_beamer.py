# SPDX-License-Identifier: AGPL-3.0-or-later
"""The info-beamer package's service (deploy/info-beamer, roadmap 9.4) against the real player API."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

from apps.evacuation import services
from apps.screens import services as screen_services

from .conftest import tf

pytestmark = pytest.mark.django_db
PATH = Path(settings.BASE_DIR) / "deploy" / "info-beamer" / "service"


def load():
    loader = importlib.machinery.SourceFileLoader("evac_info_beamer_service", str(PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def client_http(client):
    """The service's ``request`` function backed by Django's test client."""
    def request(method, url, headers, body):
        path = url.split("://", 1)[1].split("/", 1)[1]
        extra = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items() if k != "Content-Type"}
        if method == "GET":
            r = client.get("/" + path, **extra)
        else:
            r = client.post("/" + path, data=body or b"", content_type=headers.get("Content-Type", "application/json"),
                            **extra)
        return r.status_code, (r.json() if r.content and r["Content-Type"].startswith("application/json")
                               else None)
    return request


def test_pairs_shows_alarms_and_announcement_overlays(event, admin, tmp_path, monkeypatch):
    mod = load()
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    http = client_http(Client())
    out = tmp_path / "data.json"
    svc = mod.Service("https://evac.example.org", str(tmp_path), str(out), request=http)
    original = svc.request

    def pairing_request(method, url, headers, body):
        status, data = original(method, url, headers, body)
        if url.endswith("/player/api/pair/") and status == 201:
            shown = json.loads(out.read_text()) if out.exists() else {}
            assert shown == {} or shown["pairing"]["code"]
            screen_services.pair(event, data["code"], actor=admin, name="Pi in the foyer")
        return status, data

    svc.request = pairing_request
    assert svc.pair() is True
    assert (tmp_path / "token").read_text() == svc.token
    svc.request = original
    svc.tick()
    data = json.loads(out.read_text())
    assert data["online"] is True and data["event"] == "Demo Camp" and data["screen"] == "Pi in the foyer"
    assert data["evac"] is None and data["pairing"] is None
    services.change(event, "evacuate", actor=admin, request=tf(admin))
    svc.due["evac"] = 0
    svc.tick()
    evac = json.loads(out.read_text())["evac"]
    assert evac["state"] == "evacuate" and evac["takeover"] is True and evac["label"]


def test_keeps_the_last_state_offline_and_repairs_after_revocation(tmp_path):
    mod = load()
    calls = []
    alarm = {"enabled": True, "payload": {"state": "evacuate", "takeover": True, "label": "Evacuate", "seq": 3,
                                          "texts": ["Leave now"], "guidance": {"arrow": "left"}}}
    answers = {"config/": (200, {"event": {"name": "Camp", "timezone": "Europe/Berlin"}, "screen": {"name": "S"}}),
               "evacuation/state/": (200, alarm), "playlists/program/": (200, {"program": {}}),
               "heartbeat/": (200, {})}

    def http(method, url, headers, body):
        calls.append(url)
        return answers[url.split("/player/api/", 1)[1]]

    out = tmp_path / "data.json"
    (tmp_path / "token").write_text("evs_x")
    now = [1_000_000.0]
    svc = mod.Service("https://e.example", str(tmp_path), str(out), request=http, clock=lambda: now[0])
    svc.tick()
    assert json.loads(out.read_text())["evac"]["arrow"] == "left"
    answers["evacuation/state/"] = (0, None)  # EVAC unreachable
    now[0] += 5
    svc.tick()
    data = json.loads(out.read_text())
    assert data["online"] is False and data["evac"]["state"] == "evacuate"  # the alarm stays up
    answers["evacuation/state/"] = (401, None)  # screen revoked
    now[0] += 5
    svc.tick()
    assert svc.token == "" and not (tmp_path / "token").exists()


def test_overlays_and_views():
    mod = load()
    program = {"overlays": [{"style": "ticker", "title": "Doors", "text": "open", "rank": 1, "windows": [[0, 10]]},
                            {"style": "banner", "title": "Old", "windows": [[0, 1]]}],
               "entries": [{"source": "announcement", "name": "Storm", "priority": 5, "windows": [[5, 20]]}]}
    assert [o["title"] for o in mod.overlays_now(program, 6)] == ["Storm", "Doors"]
    assert mod.evac_view({"enabled": True, "payload": {"state": "normal"}}) is None
    assert mod.evac_view({"enabled": False}) is None
    assert mod.utc_offset("Europe/Berlin", 1_780_000_000) in (3600, 7200)
