# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ``evac`` CLI against the real API (requests routed into the Django test client)."""
import json

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.api import cli


class _Resp:
    def __init__(self, r):
        self.status_code = r.status_code
        self.content = r.content
        self.text = r.content.decode()

    def json(self):
        return json.loads(self.content)


@pytest.fixture
def run(monkeypatch, admin, event, capsys):
    _tok, raw = ServiceToken.issue(name="cli", owner=admin, created_with_2fa=True)
    api = APIClient()

    def request(self, method, url, params=None, json=None, timeout=None):
        path = url.split("http://evac.test")[1]
        api.credentials(**({"HTTP_AUTHORIZATION": self.headers["Authorization"]} if "Authorization" in self.headers
                           else {}))
        fn = getattr(api, method.lower())
        if method == "GET":
            return _Resp(fn(path, params or {}))
        return _Resp(fn(path, json, format="json"))

    monkeypatch.setattr("requests.Session.request", request)

    def go(*argv):
        code = cli.main(["--url", "http://evac.test", "--token", raw, *argv])
        return code, capsys.readouterr().out

    return go


@pytest.mark.django_db
def test_cli_commands(run, tmp_path):
    code, out = run("health")
    assert code == 0 and out.startswith("ok - EVAC")
    assert "root@example.org" in run("whoami")[1]
    assert "demo" in run("events", "list")[1]
    assert '"slug": "demo"' in run("events", "show", "demo")[1]
    dump = tmp_path / "demo.json"
    run("events", "export", "demo", "-o", str(dump))
    assert json.loads(dump.read_text())["event"]["slug"] == "demo"
    assert "imported as demo-copy" in run("events", "import", str(dump), "--new-slug", "demo-copy")[1]
    assert "now setup" in run("events", "transition", "demo", "setup")[1]
    assert "inactive" in run("modules", "demo", "--set", "venues=off")[1]
    assert "event.state_changed" in run("audit", "demo")[1]
    code, out = run("audit-verify")
    assert code == 0 and "OK" in out
    assert "cli" in run("tokens")[1]
    assert '"status": "ok"' in run("--json", "health")[1]


@pytest.mark.django_db
def test_cli_errors(run):
    with pytest.raises(SystemExit):
        run("events", "show", "missing")
    with pytest.raises(SystemExit):
        run("modules", "demo", "--set", "venues=maybe")
    with pytest.raises(SystemExit):
        run("events", "transition", "demo")
