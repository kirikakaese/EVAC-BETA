#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 4 gate (roadmap): EVAC against a running DIAL demo. ``make dial-e2e`` runs it; CI too.

DIAL runs as it does in production: a web server, a Celery worker (webhooks are delivered asynchronously) and Redis,
with the dummy PBX/DECT backends and the emergency, messaging and IVR features on. EVAC runs as a server with demo
data. The script checks the gate:

1. a DIAL emergency call (``incident-log`` hook) arms an evacuation request in EVAC (trigger policy);
2. an EVAC alarm rings DIAL's handsets (emergency broadcast), and DIAL's broadcast echo does not loop back;
3. an announcement recorded by phone in DIAL lands in EVAC's approval queue with the recording as its audio;
4. DIAL's phonebook, numbers, info pages and DECT status feed EVAC widgets.

    DIAL_DIR=../DIAL-BETA python scripts/dial_e2e.py      (DIAL checkout with its .venv; redis-server on PATH)
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import struct
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


def find_dial() -> Path:
    for p in (os.environ.get("DIAL_DIR", ""), ROOT.parent / "DIAL-BETA", ROOT.parent / "dial-beta"):
        if p and (Path(p) / "manage.py").is_file() and (Path(p) / "dial").is_dir():
            return Path(p).resolve()
    raise SystemExit("DIAL checkout not found: set DIAL_DIR")


def wait_http(url: str, what: str, procs: list[subprocess.Popen[bytes]] = ()) -> None:  # type: ignore[assignment]
    for _ in range(240):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except urllib.error.HTTPError:
            return  # it answers
        except OSError:
            time.sleep(0.25)
    raise SystemExit(f"{what} did not start")


class App:
    def __init__(self, name: str, cwd: Path, python: str, env: dict[str, str], prelude: str) -> None:
        self.name, self.cwd, self.python, self.env, self.prelude = name, cwd, python, env, prelude
        self.procs: list[subprocess.Popen[bytes]] = []
        self.log = open(Path(env["E2E_TMP"]) / f"{name}.log", "ab")  # noqa: SIM115 - closed by stop()

    def manage(self, *args: str) -> str:
        r = subprocess.run([self.python, "manage.py", *args], cwd=self.cwd, env=self.env, capture_output=True,
                           text=True, timeout=300)
        if r.returncode != 0:
            raise SystemExit(f"[{self.name}] manage.py {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def py(self, code: str) -> dict:
        text = self.manage("shell", "-c", f"import json\ndef out(d): print('{MARK}' + json.dumps(d, default=str))\n"
                           + self.prelude + code)
        line = next((ln for ln in text.splitlines() if ln.startswith(MARK)), None)
        if line is None:
            raise SystemExit(f"[{self.name}] no result:\n{text}")
        return json.loads(line[len(MARK):])

    def spawn(self, *args: str) -> None:
        self.procs.append(subprocess.Popen(list(args), cwd=self.cwd, env=self.env, stdout=self.log,
                                           stderr=subprocess.STDOUT))

    def stop(self) -> None:
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        self.log.close()


def step(text: str) -> None:
    print(f"• {text}", flush=True)


def expect(cond: bool, text: str, detail: object = "") -> None:
    if not cond:
        raise SystemExit(f"FAILED: {text} {detail}")
    print(f"  ✓ {text}", flush=True)


def until(fn, timeout: float = 30.0):  # type: ignore[no-untyped-def]
    end = time.time() + timeout
    value = fn()
    while not value and time.time() < end:
        time.sleep(0.5)
        value = fn()
    return value


def post(url: str, body: dict, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def wav(seconds: float = 1.0) -> bytes:
    rate = 8000
    pcm = b"".join(struct.pack("<h", int(8000 * ((i // 20) % 2 * 2 - 1))) for i in range(int(rate * seconds)))
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE" + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
            rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


def main() -> int:  # noqa: PLR0915 - a linear script
    dial_dir = find_dial()
    dial_py = str(dial_dir / ".venv" / "bin" / "python") if (dial_dir / ".venv" / "bin" / "python").exists() \
        else sys.executable
    tmp = Path(tempfile.mkdtemp(prefix="evac-dial-e2e-"))
    out_dir = Path(os.environ.get("E2E_OUT", ROOT / "e2e-output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    e_port, d_port = free_port(), free_port()
    redis_url = os.environ.get("DIAL_REDIS_URL", "")
    redis_proc = None
    if not redis_url:
        r_port = free_port()
        redis_proc = subprocess.Popen(["redis-server", "--port", str(r_port), "--save", "", "--appendonly", "no"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        redis_url = f"redis://127.0.0.1:{r_port}/0"
    (tmp / "recordings").mkdir()
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DATABASE_URL", "REDIS_URL"))}
    dial = App("dial", dial_dir, dial_py, {
        **base_env, "E2E_TMP": str(tmp), "DJANGO_SETTINGS_MODULE": "dial.settings.dev",
        "DATABASE_URL": f"sqlite:///{tmp / 'dial.sqlite3'}?timeout=30", "REDIS_URL": redis_url, "DEBUG": "1",
        "CELERY_TASK_ALWAYS_EAGER": "0", "SECRET_KEY": "dial-e2e-only-" + "x" * 40, "ALLOWED_HOSTS": "*",
        "MEDIA_ROOT": str(tmp / "dial-media"), "DIAL_RECORDING_DIR": str(tmp / "recordings"),
        "DIAL_PUBLIC_URL": f"http://127.0.0.1:{d_port}", "DIAL_PBX_BACKEND": "apps.pbx.backends.dummy.DummyPBX",
        "DIAL_DECT_BACKEND": "apps.dect.backends.dummy.DummyDECT", "DIAL_EARLY_ACCESS_PASSWORD": "",
        "DIAL_FEATURES": "phonebook,callgroups,voicemail,stats,guest_extensions,waitlist,webhooks,emergency,"
                         "messaging,ivr",
        "PYTHONUNBUFFERED": "1"}, "from apps.events.models import Event\nevent = Event.objects.get(slug='demo')\n")
    evac = App("evac", ROOT, PY, {
        **base_env, "E2E_TMP": str(tmp), "DJANGO_SETTINGS_MODULE": "evac.settings.dev",
        "DATABASE_URL": f"sqlite:///{tmp / 'evac.sqlite3'}", "REDIS_URL": "", "MEDIA_ROOT": str(tmp / "evac-media"),
        "SECRET_KEY": "evac-e2e-only-" + "x" * 40, "EVAC_SECRETS_KEYS": "", "EVAC_EARLY_ACCESS_PASSWORD": "",
        "ALLOWED_HOSTS": "*", "CELERY_TASK_ALWAYS_EAGER": "1", "PYTHONUNBUFFERED": "1"},
        "from apps.events.models import Event\nfrom apps.accounts.models import User\n"
        "event = Event.objects.get(slug='demo')\nadmin = User.objects.get(email='admin@evac.local')\n"
        "from apps.extensions.models import ExtensionConfig\n"
        "def cfg(): return ExtensionConfig.objects.get(extension='dial', event=event)\n")
    try:
        step("DIAL: migrate, demo data, a service token for EVAC")
        dial.manage("migrate", "--noinput")
        dial.manage("seed_demo", "--no-cdr")
        text = dial.manage("dial_token", "--user", "admin@dial.local", "--name", "evac", "--event", "demo",
                           "--scopes", *("events:read pages:read phonebook:read dect:read ivr:read emergency:read "
                                         "emergency:write messaging:write").split(), "--export")
        token = next(w for w in text.replace("=", " ").split() if w.startswith("dial_"))
        expect(token.startswith("dial_"), "service token minted")

        step("EVAC: migrate, demo data, the DIAL link")
        evac.manage("migrate", "--noinput")
        evac.manage("evac_seed_demo")
        link = evac.py(
            "from apps.core import modules, settings_store\n"
            "from apps.core.registry import registry\nfrom apps.extensions import services as ext\n"
            "modules.set_instance('evacuation', True); modules.set_event(event, 'evacuation', True)\n"
            "modules.acknowledge(event, 'evacuation', user=admin)\n"
            "settings_store.save('evacuation', 'event', str(event.pk), {'model': 'staged'}, event=event)\n"
            "modules.set_event(event, 'widgets', True)\n"
            "spec = registry.get_extension('dial')\n"
            "c = ext.save_config(ext.get_or_new(spec, event), settings_values={'base_url': "
            f"'http://127.0.0.1:{d_port}', 'event': 'demo', 'important_numbers': '1100 = Info desk'}}, "
            f"secret_values={{'token': '{token}'}}, features={{f.key: True for f in spec.features}}, enabled=True)\n"
            "secret = ext.regenerate_webhook_secret(c)\n"
            "out({'id': str(c.pk), 'secret': secret})")

        step("start DIAL (web + Celery worker) and EVAC")
        dial.spawn(dial_py, "manage.py", "runserver", f"127.0.0.1:{d_port}", "--noreload")
        # the demo seed queued provisioning jobs for the dummy PBX; a backlog only competes for the SQLite lock
        subprocess.run([str(Path(dial_py).parent / "celery"), "-A", "dial", "purge", "-f"], cwd=dial_dir, env=dial.env,
                       capture_output=True, timeout=60, check=False)
        dial.spawn(str(Path(dial_py).parent / "celery"), "-A", "dial", "worker", "-l", "warning", "--pool", "solo")
        evac.spawn(PY, "manage.py", "runserver", f"127.0.0.1:{e_port}", "--noreload")
        wait_http(f"http://127.0.0.1:{d_port}/api/v1/health/", "DIAL")
        wait_http(f"http://127.0.0.1:{e_port}/healthz", "EVAC")
        hook = f"http://127.0.0.1:{e_port}/api/v1/extensions/dial/{link['id']}/webhook/"
        dial.py("from apps.events.models import Webhook\n"
                f"Webhook.objects.create(event=event, name='evac', url='{hook}', secret='{link['secret']}', "
                "event_types=[], is_active=True); out({})")

        step("4.1 test connection")
        r = evac.py("from apps.extensions import services as ext\nres = ext.test_connection(cfg(), user=admin)\n"
                    "out({'ok': res.ok, 'message': res.message})")
        expect(r["ok"], "EVAC reaches DIAL with the token", r["message"])

        step("gate 1: an emergency call in DIAL arms an alarm in EVAC")
        got = post(f"http://127.0.0.1:{d_port}/api/v1/emergency/incident-log/",
                   {"event": "demo", "number": "112", "caller": "2001"}, {"X-DIAL-PBX-Secret": "dial"})
        expect(bool(got.get("handled")), "DIAL logged the incident", got)
        req = until(lambda: evac.py(
            "from apps.evacuation.models import EvacRequest\n"
            "r = EvacRequest.objects.filter(event=event, source='dial').first()\n"
            "out(r and {'status': r.status, 'state': r.state, 'reason': r.reason})"))
        expect(bool(req) and req["status"] == "pending", "EVAC armed a request from source DIAL", req)
        expect("112" in req["reason"] and "2001" in req["reason"], "the reason names number and caller", req)

        step("gate 2: an EVAC alarm rings DIAL's handsets")
        evac.py("from apps.evacuation import services\n"
                "services.change(event, 'evacuate', actor=admin, check_perms=False, reason='e2e: fire in hall A')\n"
                "out({})")
        b = until(lambda: evac.py("from extensions.dial.models import Broadcast\n"
                                  "b = Broadcast.objects.filter(source='evacuation').first()\n"
                                  "out(b and {'status': b.status, 'detail': b.detail, 'text': b.text})"))
        expect(bool(b) and b["status"] == "sent", "EVAC's broadcast was accepted by DIAL", b)
        d = dial.py("from apps.emergency.models import BroadcastAnnouncement\n"
                    "x = BroadcastAnnouncement.objects.filter(event=event).order_by('-pk').first()\n"
                    "out(x and {'text': x.text, 'targets': x.targets})")
        expect(bool(d) and d["text"] == "Evacuate" and d["targets"] > 0,
               f"DIAL rang {d and d['targets']} handsets with “Evacuate”", d)
        time.sleep(4)  # DIAL's worker posts the broadcast echo (emergency.triggered, kind broadcast)
        n = evac.py("from apps.evacuation.models import EvacRequest\nfrom apps.extensions.models import "
                    "InboundDelivery\nout({'req': EvacRequest.objects.filter(source='dial').count(), "
                    "'in': InboundDelivery.objects.filter(config=cfg()).count()})")
        expect(n["req"] == 1 and n["in"] >= 2, "DIAL's broadcast echo arrived and was not taken as a new alarm", n)

        step("gate 3: an announcement recorded by phone lands in the approval queue")
        code = dial.py("from apps.extensions.models import Extension\nfrom apps.ivr.services import "
                       "ensure_record_code\next = Extension.objects.get(event=event, number='4000')\n"
                       "out({'code': ensure_record_code(ext)})")["code"]
        rec = tmp / "recordings" / "demo-4000-e2e.wav"
        rec.write_bytes(wav())
        got = post(f"http://127.0.0.1:{d_port}/api/v1/pbx/hooks/announcement-recorded/",
                   {"event": "demo", "code": code, "file": str(rec), "duration": 1}, {"X-DIAL-PBX-Secret": "dial"})
        expect(bool(got.get("handled")), "DIAL took the recording", got)
        ann = until(lambda: evac.py(
            "from extensions.dial.models import Recording\nr = Recording.objects.filter(status='imported').first()\n"
            "out(r and {'status': r.announcement.status, 'audio': r.announcement.speech_recorded, "
            "'file': r.speech_file, 'title': r.announcement.title, 'detail': r.detail})"), timeout=45)
        expect(bool(ann) and ann["status"] == "pending", "EVAC created an announcement waiting for approval", ann)
        expect(ann["audio"] and bool(ann["file"]), "the phone recording is its audio", ann)
        dl = evac.py("from extensions.dial.models import Recording\nr = Recording.objects.first()\n"
                     "out({'id': r.dial_announcement})")
        print("  · fetched from " + ("DIAL's audio endpoint" if dl["id"] else "DIAL's /media/ (older DIAL)"),
              flush=True)

        step("gate 4: DIAL data feeds EVAC widgets")
        w = evac.py("from extensions.dial import presets\nfrom apps.widgets.models import Feed\n"
                    "made = presets.install(event, actor=admin)\n"
                    "feeds = {f.source: (f.status, f.error, f.snapshot) for f in Feed.objects.filter(event=event, "
                    "source__startswith='dial.')}\n"
                    "out({'widgets': len(made), 'feeds': {k: v[:2] for k, v in feeds.items()}, "
                    "'numbers': [i['call'] + ': ' + i['label'] for i in feeds['dial.numbers'][2]['items']], "
                    "'phonebook': feeds['dial.phonebook'][2]['count'], 'pages': feeds['dial.pages'][2]['count'], "
                    "'rfps': feeds['dial.dect'][2]['rfps']})")
        expect(w["widgets"] == 5, "five DIAL widgets installed")
        expect(all(s == "ok" for s, _e in w["feeds"].values()), "every DIAL feed fetched", w["feeds"])
        expect("Call 1100: Info desk" in w["numbers"] and any(n.startswith("Call 112") for n in w["numbers"]),
               "call X for Y: own and emergency numbers", w["numbers"])
        expect(w["phonebook"] > 0, f"{w['phonebook']} phonebook entries")
        print(f"  · {w['pages']} info pages, {w['rfps']} DECT base stations", flush=True)

        step("info pages and DECT alerts from DIAL reach EVAC")
        dial.py("from apps.pages.models import InfoPage\nfrom apps.pages.views import notify\n"
                "from apps.accounts.models import User\nadmin = User.objects.get(email='admin@dial.local')\n"
                "p = InfoPage.objects.create(event=event, slug='phones', title='Phones at camp', body="
                "'Dial **1100** for the info desk.\\n\\n- 112: medics\\n- 110: security')\n"
                "notify(p, 'create', admin)\n"
                "from apps.dect.models import RFP\nfrom apps.dect.services import open_alert\n"
                "rfp = RFP.objects.filter(event=event).first()\n"
                "open_alert(event, 'rfp.down', 'critical', f'{rfp.name} is down', rfp=rfp)\nout({})")
        pages = until(lambda: evac.py("from apps.widgets.models import Feed\n"
                                      "f = Feed.objects.get(event=event, source='dial.pages')\n"
                                      "out([i['title'] for i in (f.snapshot or {}).get('items', [])])"))
        expect(pages == ["Phones at camp"], "page.updated refreshed the info pages feed", pages)
        alert = until(lambda: evac.py("from extensions.dial.models import DectAlert\n"
                                      "a = DectAlert.objects.first()\nout(a and {'kind': a.kind, 'msg': a.message})"))
        expect(bool(alert) and alert["kind"] == "rfp.down", "the DECT alert is on EVAC's DIAL page", alert)

        if os.environ.get("DIAL_E2E_KEEP"):
            (out_dir / "dial-e2e.json").write_text(json.dumps({
                "evac": f"http://127.0.0.1:{e_port}", "dial": f"http://127.0.0.1:{d_port}", "tmp": str(tmp)}))
            print(f"servers kept running (EVAC :{e_port}, DIAL :{d_port}); press Ctrl-C to stop", flush=True)
            while True:
                time.sleep(3600)
        print("DIAL e2e: all checks passed", flush=True)
        return 0
    finally:
        evac.stop()
        dial.stop()
        if redis_proc is not None:
            redis_proc.terminate()
        if not os.environ.get("DIAL_E2E_KEEP"):
            print(f"(logs in {tmp})") if os.environ.get("DIAL_E2E_DEBUG") else shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
