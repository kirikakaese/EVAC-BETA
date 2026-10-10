#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Central/node sync with two real EVAC instances (ADR-0036). ``make node-e2e`` runs it; CI too.

Central runs as a server with its own database; the node is a second database in ``EVAC_MODE=node`` that talks to
central only through ``manage.py evac_node``. The script checks: enrolment, checkout and the first (seed)
snapshot, an alarm raised on site reaching central through the op-log, an alarm from central's control room
forwarded to the node, a partition (central down while the node raises an alarm, caught up afterwards), and the
check-in (alarm counter handed back, the node a read-only copy).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable
MARK = "@@"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Instance:
    def __init__(self, role: str, tmp: Path) -> None:
        self.role = role
        self.env = {**os.environ, "DJANGO_SETTINGS_MODULE": "evac.settings.dev",
                    "DATABASE_URL": f"sqlite:///{tmp / role}.sqlite3", "MEDIA_ROOT": str(tmp / f"{role}-media"),
                    "REDIS_URL": "", "EVAC_MODE": role, "SECRET_KEY": f"e2e-{role}-only-" + "x" * 40,
                    "EVAC_SECRETS_KEYS": "", "EVAC_EARLY_ACCESS_PASSWORD": "", "ALLOWED_HOSTS": "*",
                    "PYTHONUNBUFFERED": "1"}
        self.server: subprocess.Popen[bytes] | None = None

    def manage(self, *args: str, check: bool = True) -> str:
        r = subprocess.run([PY, "manage.py", *args], cwd=ROOT, env=self.env, capture_output=True, text=True,
                           timeout=300)
        if check and r.returncode != 0:
            raise SystemExit(f"[{self.role}] manage.py {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def py(self, code: str) -> dict:
        """Run ``code`` in the instance; it must ``out(dict)``."""
        prelude = ("import json\n"
                   "from apps.events.models import Event\n"
                   "from apps.accounts.models import User\n"
                   f"def out(d): print('{MARK}' + json.dumps(d, default=str))\n"
                   "event = Event.objects.get(slug='demo')\n"
                   "admin = User.objects.get(email='admin@evac.local')\n")
        text = self.manage("shell", "-c", prelude + code)
        line = next((ln for ln in text.splitlines() if ln.startswith(MARK)), None)
        if line is None:
            raise SystemExit(f"[{self.role}] no result:\n{text}")
        return json.loads(line[len(MARK):])

    def start(self, port: int) -> None:
        self.server = subprocess.Popen([PY, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"], cwd=ROOT,
                                       env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
                return
            except OSError:
                time.sleep(0.25)
        raise SystemExit("central did not start")

    def stop(self) -> None:
        if self.server is not None:
            self.server.terminate()
            self.server.wait(timeout=20)
            self.server = None


def step(text: str) -> None:
    print(f"• {text}", flush=True)


def expect(cond: bool, text: str) -> None:
    if not cond:
        raise SystemExit(f"FAILED: {text}")
    print(f"  ✓ {text}", flush=True)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="evac-node-e2e-"))
    central, node = Instance("central", tmp), Instance("node", tmp)
    port = free_port()
    try:
        step("migrate both, demo data on central")
        central.manage("migrate", "--noinput")
        node.manage("migrate", "--noinput")
        central.manage("evac_seed_demo")
        reg = central.py(
            "from apps.core import modules, settings_store\n"
            "modules.set_instance('evacuation', True); modules.set_event(event, 'evacuation', True)\n"
            "settings_store.save('evacuation', 'event', str(event.pk), {'model': 'zones'}, event=event)\n"
            "from apps.nodes import central\n"
            "n, code = central.register('Hall A rack', actor=admin)\n"
            "from apps.screens.models import Screen\n"
            "out({'code': code, 'node': str(n.pk), 'screens': Screen.objects.filter(event=event).count()})")
        central.start(port)

        step("enrol the node and check the event out to it")
        print("  " + node.manage("evac_node", "enrol", "--central", f"http://127.0.0.1:{port}", "--code",
                                 reg["code"]).strip())
        central.py("from apps.nodes import central\nfrom apps.nodes.models import Node\n"
                   f"central.checkout(event, Node.objects.get(pk='{reg['node']}'), actor=admin); out({{}})")
        sync = json.loads(node.manage("evac_node", "sync"))
        expect(sync["events"][0]["snapshot"] == "applied", "the node applied the seed snapshot")
        got = node.py("from apps.screens.models import Screen\nfrom apps.evacuation import alarmkey\n"
                      "out({'screens': Screen.objects.filter(event=event).count(), "
                      "'key': bool(alarmkey.export_private(event)), 'admin': admin.has_usable_password()})")
        expect(got["screens"] == reg["screens"], f"the node has the event's {reg['screens']} screens")
        expect(got["key"], "the alarm key's private half arrived sealed and opens on the node")
        expect(got["admin"], "people can sign in on the node")

        step("an alarm raised on site reaches central")
        node.py("from apps.evacuation import services\n"
                "services.change(event, 'evacuate', actor=admin, check_perms=False, reason='e2e smoke'); out({})")
        node.manage("evac_node", "sync")
        c = central.py("from apps.evacuation.models import EvacState\nfrom apps.core.models import AuditLog\n"
                       "out({'state': EvacState.objects.get(event=event, zone=None).state, "
                       "'audit': AuditLog.objects.filter(scope__node='Hall A rack').count()})")
        expect(c["state"] == "evacuate", "central shows the node's alarm")
        expect(c["audit"] > 0, "the node's audit entries joined central's chain")

        step("the all clear from central's control room runs on the node")
        c = central.py("from apps.evacuation import triggers\n"
                       "o = triggers.trigger(event, 'all_clear', source='web', actor=admin, check_perms=False)\n"
                       "out({'result': o.result})")
        expect(c["result"] == "forwarded", "central forwards instead of changing")
        node.manage("evac_node", "sync")
        n = node.py("from apps.evacuation.models import EvacState\n"
                    "out({'state': EvacState.objects.get(event=event, zone=None).state})")
        expect(n["state"] == "all_clear", "the node ran it")
        c = central.py("from apps.evacuation.models import EvacState\nfrom apps.nodes.models import ProxiedAction\n"
                       "out({'state': EvacState.objects.get(event=event, zone=None).state, "
                       "'action': ProxiedAction.objects.get().status})")
        expect(c["state"] == "all_clear" and c["action"] == "done", "and central sees the result")

        step("partition: central down while the node raises an alarm")
        central.stop()
        node.py("from apps.evacuation import services\n"
                "services.change(event, 'evacuate', actor=admin, check_perms=False, reason='during outage'); out({})")
        down = json.loads(node.manage("evac_node", "sync"))
        expect("error" in down, "the node keeps working and notes central unreachable")
        central.start(port)
        node.manage("evac_node", "sync")
        c = central.py("from apps.evacuation.models import EvacState\n"
                       "out({'state': EvacState.objects.get(event=event, zone=None).state})")
        expect(c["state"] == "evacuate", "central caught up after the outage")

        step("check-in")
        central.py("from apps.nodes import central\ncentral.request_checkin(central.checkout_of(event), actor=admin)\n"
                   "out({})")
        res = json.loads(node.manage("evac_node", "sync"))
        expect(res["events"][0].get("checkin") == "checked_in", "the node handed the event back")
        n = node.py("from apps.evacuation import feed\nout({'seq': feed.current_seq(event)})")
        c = central.py("from apps.nodes.models import Checkout\nfrom apps.evacuation import feed\n"
                       "out({'state': Checkout.objects.get().state, 'seq': feed.current_seq(event)})")
        expect(c["state"] == "checked_in", "central runs the event again")
        expect(c["seq"] > n["seq"], "central's alarm counter is past the node's (screens accept its next message)")
        n = node.py("from apps.evacuation import services, machine\n"
                    "try:\n    services.change(event, 'normal', actor=admin, check_perms=False); r = 'changed'\n"
                    "except machine.Refused as e:\n    r = e.code\nout({'r': r})")
        expect(n["r"] == "checked_out", "the node keeps a read-only copy")
        print("node sync end-to-end: all checks passed")
        return 0
    finally:
        central.stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
