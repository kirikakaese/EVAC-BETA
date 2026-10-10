#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Load test (roadmap 3.12, brief §8.5): N screens on WebSockets receive an alarm within 2 s (p95).

Starts a throw-away EVAC with demo data, pairs N screens, connects N WebSocket players, raises an alarm through
the REST API and measures, per player, the time from the API call to the arrival of its signed evacuation message.
Then steps the alarm up and measures again. Exits 1 when a player missed a message or p95 is over the target.

    make load                                  (500 players)
    python scripts/load_ws.py --players 200 --target-ms 2000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable
MARK = "@@"


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)] if ordered else float("nan")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Server:
    def __init__(self, tmp: Path) -> None:
        self.env = {**os.environ, "DJANGO_SETTINGS_MODULE": "evac.settings.dev",
                    "DATABASE_URL": f"sqlite:///{tmp}/load.sqlite3", "MEDIA_ROOT": str(tmp / "media"),
                    "REDIS_URL": "", "EVAC_EARLY_ACCESS_PASSWORD": "", "ALLOWED_HOSTS": "*", "DEBUG": "0",
                    "LOG_LEVEL": "WARNING", "PYTHONUNBUFFERED": "1"}
        self.proc: subprocess.Popen[bytes] | None = None

    def manage(self, *args: str) -> str:
        r = subprocess.run([PY, "manage.py", *args], cwd=ROOT, env=self.env, capture_output=True, text=True,
                           timeout=600)
        if r.returncode != 0:
            raise SystemExit(f"manage.py {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def py(self, code: str) -> dict:
        text = self.manage("shell", "-c", f"import json\ndef out(d): print('{MARK}' + json.dumps(d))\n{code}")
        line = next(ln for ln in text.splitlines() if ln.startswith(MARK))
        return json.loads(line[len(MARK):])

    def start(self, port: int) -> None:
        self.proc = subprocess.Popen([PY, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"], cwd=ROOT,
                                     env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(240):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
                return
            except OSError:
                time.sleep(0.25)
        raise SystemExit("server did not start")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait(timeout=20)


SETUP = """
from apps.core import modules, settings_store
from apps.events.models import Event
from apps.accounts.models import ServiceToken, User
from apps.evacuation.models import EvacPolicy
from apps.screens.models import Screen
event = Event.objects.get(slug="demo")
admin = User.objects.get(email="admin@evac.local")
modules.set_instance("evacuation", True); modules.set_event(event, "evacuation", True)
modules.acknowledge(event, "evacuation", user=admin)
settings_store.save("evacuation", "event", str(event.pk), {"model": "staged"}, event=event)
EvacPolicy.objects.get_or_create(event=event, source="api", state="", zone=None, defaults={"action": "execute"})
_t, api = ServiceToken.issue(name="load", owner=admin, event=event, scopes=["evacuation:write"], created_with_2fa=True)
tokens = []
for i in range(N):
    s = Screen(event=event, name=f"load-{i:04d}")
    tokens.append(s.issue_token())
    s.save()
out({"api": api, "tokens": tokens})
"""


async def player(url: str, token: str, results: dict[str, list[float]], ready: asyncio.Event,
                 connected: list[int], stop: asyncio.Event, clock: dict[str, float]) -> None:
    async with websockets.connect(url, max_size=2 ** 22, open_timeout=60, ping_interval=None) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token, "since": 0}))
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "hello":
                break
        connected[0] += 1
        if connected[0] == clock["n"]:
            ready.set()
        while not stop.is_set():
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.5))
            except TimeoutError:
                continue
            if msg.get("type") == "evac.state":
                state = msg["data"].get("state", "")
                if state in clock and "sig" in msg["data"]:
                    results.setdefault(state, []).append((time.monotonic() - clock[state]) * 1000)


def trigger(base: str, api: str, state: str) -> None:
    req = urllib.request.Request(f"{base}/api/v1/events/demo/evacuation/trigger/", method="POST",
                                 data=json.dumps({"state": state, "reason": "load test"}).encode(),
                                 headers={"Authorization": f"Bearer {api}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.loads(r.read())
    if body.get("result") != "executed":
        raise SystemExit(f"trigger not executed: {body}")


async def run(base: str, ws_url: str, api: str, tokens: list[str], target: float) -> int:
    results: dict[str, list[float]] = {}
    ready, stop = asyncio.Event(), asyncio.Event()
    connected = [0]
    clock: dict[str, float] = {"n": len(tokens)}
    started = time.monotonic()
    tasks = []
    for i, t in enumerate(tokens):
        tasks.append(asyncio.create_task(player(ws_url, t, results, ready, connected, stop, clock)))
        if i % 50 == 49:
            await asyncio.sleep(0.05)  # do not open all sockets in the same millisecond
    await asyncio.wait_for(ready.wait(), timeout=180)
    print(f"{len(tokens)} players connected in {time.monotonic() - started:.1f} s", flush=True)
    failed = 0
    for state in ("attention", "evacuate"):
        await asyncio.sleep(1)
        clock[state] = time.monotonic()
        await asyncio.get_running_loop().run_in_executor(None, trigger, base, api, state)
        deadline = time.monotonic() + max(10.0, target / 1000 * 5)
        while len(results.get(state, [])) < len(tokens) and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        got = results.get(state, [])
        q = pct(got, 0.95)
        print(f"{state}: {len(got)}/{len(tokens)} players, p50 {pct(got, 0.5):.0f} ms, p95 {q:.0f} ms, "
              f"max {pct(got, 1.0):.0f} ms (target p95 ≤ {target:.0f} ms)", flush=True)
        if len(got) < len(tokens) or not q <= target:
            failed += 1
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    return failed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--players", type=int, default=500)
    ap.add_argument("--target-ms", type=float, default=2000.0)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="evac-load-"))
    server = Server(tmp)
    try:
        server.manage("migrate", "--noinput")
        server.manage("evac_seed_demo")
        data = server.py(f"N = {args.players}\n" + SETUP)
        port = free_port()
        server.start(port)
        failed = asyncio.run(run(f"http://127.0.0.1:{port}", f"ws://127.0.0.1:{port}/ws/screen/", data["api"],
                                 data["tokens"], args.target_ms))
        print("load test: " + ("FAILED" if failed else "passed"))
        return 1 if failed else 0
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
