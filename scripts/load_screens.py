#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phase 9 gate (brief §13: 1,000 screens per instance): N simulated screens through a whole session.

Starts a throw-away EVAC with demo data and a published default layout, pairs N screens and lets every simulated
screen do what the player does:

1. **boot**: ``config``, ``program``, ``bundle`` and the evacuation state over HTTP (with its screen token);
2. **connect** the WebSocket and authenticate;
3. **heartbeat** every ``--heartbeat`` seconds for ``--minutes`` (with the player's report: version, resolution,
   slide, memory) and wait for each acknowledgement;
4. a **content change** (an announcement is published): every screen gets ``program.changed`` and fetches its
   program again;
5. an **alarm** through the REST API: every screen gets its signed evacuation state.

It reports p50/p95/max per step and fails when a screen misses something or a target is exceeded. The simulated
screens live in separate processes (``--workers``) so the load generator is not the bottleneck.

With ``--production`` the server runs as deployed (deploy/entrypoint.sh): gunicorn with ASGI workers for HTTP and,
separately, for WebSockets (``--ws-workers``), a Celery worker for deliveries, Redis between them and the database from
``LOAD_DATABASE_URL`` (PostgreSQL), ``LOAD_REDIS_URL`` (default ``redis://127.0.0.1:6379/15``). Without it, one
``runserver`` process with SQLite and in-memory layers (a smoke test, not a capacity figure).

    python scripts/load_screens.py --screens 1000 --production
    python scripts/load_screens.py --screens 200 --minutes 0.5 --workers 2
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import multiprocessing as mp
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable
MARK = "@@"
# boot is a cold start of every screen in the same second (after a power cut): players show their cached content
# and alarm bundle meanwhile, so it is a throughput target (ADR-0047); the others are what people see
TARGETS_MS = {"boot": 30000, "heartbeat": 1000, "change": 2000, "refetch": 5000, "alarm": 2000}
FLEET_BOOT_S = 180  # all screens booted and connected


def pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)] if ordered else float("nan")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


SETUP = """
from apps.content import services as content
from apps.content.models import Layout
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
lay = Layout.objects.filter(event=event).first() or content.create_layout(event, name="Load", key="load", actor=admin)
content.publish_layout(lay, actor=admin)
_t, api = ServiceToken.issue(name="load", owner=admin, event=event,
                             scopes=["evacuation:write", "announcements:write"], created_with_2fa=True)
tokens = []
for i in range(N):
    s = Screen(event=event, name=f"load-{i:04d}")
    tokens.append(s.issue_token())
    s.save()
out({"api": api, "tokens": tokens})
"""


class Server:
    def __init__(self, tmp: Path, production: bool, web_workers: int, ws_workers: int = 3) -> None:
        self.production, self.web_workers, self.ws_workers = production, web_workers, ws_workers
        db = os.environ.get("LOAD_DATABASE_URL") or f"sqlite:///{tmp}/load.sqlite3"
        redis = os.environ.get("LOAD_REDIS_URL", "redis://127.0.0.1:6379/15") if production else ""
        if production and db.startswith("sqlite"):
            raise SystemExit("--production needs LOAD_DATABASE_URL (PostgreSQL)")
        self.env = {**os.environ, "DJANGO_SETTINGS_MODULE": "evac.settings.dev", "DATABASE_URL": db,
                    "MEDIA_ROOT": str(tmp / "media"), "REDIS_URL": redis,
                    "EVAC_EARLY_ACCESS_PASSWORD": "", "ALLOWED_HOSTS": "*", "DEBUG": "0", "LOG_LEVEL": "WARNING",
                    "PYTHONUNBUFFERED": "1"}
        self.tmp = tmp
        self.procs: list[subprocess.Popen[bytes]] = []
        self.logs: list[Any] = []
        self.http = self.ws = 0

    def manage(self, *args: str) -> str:
        r = subprocess.run([PY, "manage.py", *args], cwd=ROOT, env=self.env, capture_output=True, text=True,
                           timeout=900)
        if r.returncode != 0:
            raise SystemExit(f"manage.py {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
        return r.stdout

    def py(self, code: str) -> dict:
        text = self.manage("shell", "-c", f"import json\ndef out(d): print('{MARK}' + json.dumps(d))\n{code}")
        line = next(ln for ln in text.splitlines() if ln.startswith(MARK))
        return json.loads(line[len(MARK):])

    def _spawn(self, *cmd: str) -> None:
        log = open(self.tmp / f"{Path(cmd[0]).name}-{len(self.procs)}.log", "wb")  # noqa: SIM115 - closed by stop()
        self.logs.append(log)
        self.procs.append(subprocess.Popen(list(cmd), cwd=ROOT, env=self.env, stdout=log, stderr=subprocess.STDOUT))

    def tail_logs(self, lines: int = 15) -> str:
        out = []
        for f in self.logs:
            f.flush()
            text = Path(f.name).read_text(errors="replace").splitlines()[-lines:]
            if text:
                out.append(f"--- {Path(f.name).name}\n" + "\n".join(text))
        return "\n".join(out)

    def start(self) -> None:
        bindir = Path(PY).parent
        self.http = free_port()
        if self.production:
            self.ws = free_port()
            self._spawn(str(bindir / "gunicorn"), "evac.asgi:application", "-k", "uvicorn_worker.UvicornWorker",
                        "--bind", f"127.0.0.1:{self.http}", "--workers", str(self.web_workers), "--timeout", "90")
            # the realtime service as deployed (deploy/entrypoint.sh "channels"): ASGI workers sharing the port
            self._spawn(str(bindir / "gunicorn"), "evac.asgi:application", "-k", "uvicorn_worker.UvicornWorker",
                        "--bind", f"127.0.0.1:{self.ws}", "--workers", str(self.ws_workers), "--timeout", "90")
            self._spawn(str(bindir / "celery"), "-A", "evac", "worker", "-l", "WARNING", "-c", "2")
        else:
            self.ws = self.http
            self._spawn(PY, "manage.py", "runserver", f"127.0.0.1:{self.http}", "--noreload")
        for port in {self.http, self.ws}:
            for _ in range(240):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
                    break
                except OSError:
                    time.sleep(0.25)
            else:
                raise SystemExit("server did not start")

    def stop(self) -> None:
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=30)
            except subprocess.TimeoutExpired:
                p.kill()
        for f in self.logs:
            f.close()


async def http_get(port: int, path: str, token: str) -> int:
    """A minimal HTTP/1.1 GET (no client library needed); returns the status."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Screen {token}\r\n"
                 f"Connection: close\r\n\r\n".encode())
    await writer.drain()
    data = await reader.read()
    writer.close()
    return int(data.split(b" ", 2)[1]) if data.startswith(b"HTTP/") else 0


BOOT = ("/player/api/config/", "/player/api/playlists/program/", "/player/api/content/bundle/",
        "/player/api/evacuation/state/")


class Screen:
    def __init__(self, port: int, ws_port: int, token: str, idx: int, hb: float,
                 results: dict[str, list[float]]) -> None:
        self.port, self.ws_port, self.token, self.idx, self.hb, self.r = port, ws_port, token, idx, hb, results
        self.errors: list[str] = []
        self.pending: dict[str, float] = {}

    def mark(self, step: str, ms: float) -> None:
        self.r.setdefault(step, []).append(ms)

    async def boot(self) -> None:
        t = time.monotonic()
        for path in BOOT:
            status = await http_get(self.port, path, self.token)
            if status != 200:
                self.errors.append(f"{path} {status}")
        self.mark("boot", (time.monotonic() - t) * 1000)

    async def refetch(self, spread: float) -> None:
        await asyncio.sleep(random.random() * spread)
        asked = time.time()
        status = await http_get(self.port, "/player/api/playlists/program/", self.token)
        if status != 200:
            self.errors.append(f"refetch {status}")
        self.mark("refetch", (time.time() - asked) * 1000)

    async def session(self, phases: dict[str, float], stop_at: float, connected: Any, gate: Any) -> None:
        import websockets

        async with websockets.connect(f"ws://127.0.0.1:{self.ws_port}/ws/screen/", max_size=2 ** 23,
                                      open_timeout=120, ping_interval=None) as ws:
            await ws.send(json.dumps({"type": "auth", "token": self.token, "since": 0}))
            while json.loads(await ws.recv()).get("type") != "hello":
                pass
            with connected.get_lock():
                connected.value += 1
            while not gate.value:  # every screen of every worker is connected
                await asyncio.sleep(0.05)
            await asyncio.sleep((self.idx % 100) / 100 * self.hb)  # spread the heartbeats
            next_hb = time.monotonic()
            got_change = got_alarm = False
            refetch: asyncio.Task[None] | None = None
            while time.monotonic() < stop_at and not (got_alarm and got_change):
                now = time.monotonic()
                if now >= next_hb and not phases.get("alarm"):
                    self.pending["hb"] = now
                    await ws.send(json.dumps({"type": "heartbeat", "data": {
                        "version": "load", "resolution": "1920x1080", "orientation": "landscape",
                        "slide": "load", "memory": 120.5, "uptime": int(now), "online": True}}))
                    next_hb = now + self.hb
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=0.25))
                except TimeoutError:
                    continue
                kind = msg.get("type")
                arrived = time.time()
                if kind == "heartbeat.ack" and "hb" in self.pending:
                    self.mark("heartbeat", (time.monotonic() - self.pending.pop("hb")) * 1000)
                elif kind == "program.changed" and phases.get("change") and not got_change:
                    got_change = True
                    self.mark("change", (arrived - phases["change"]) * 1000)
                    # like the player: refetch at a random moment within the server's "spread", without blocking
                    # the WebSocket (an alarm may arrive meanwhile)
                    refetch = asyncio.create_task(self.refetch(float((msg.get("data") or {}).get("spread") or 0)))
                elif kind == "evac.state" and phases.get("alarm") and not got_alarm:
                    if msg.get("data", {}).get("state") == "evacuate" and "sig" in msg.get("data", {}):
                        got_alarm = True
                        self.mark("alarm", (arrived - phases["alarm"]) * 1000)
            if refetch is not None:
                await refetch


def worker(port: int, ws_port: int, tokens: list[tuple[int, str]], hb: float, phases: Any, stop_at: float,
           connected: Any, gate: Any, out: Any) -> None:
    results: dict[str, list[float]] = {}
    screens = [Screen(port, ws_port, t, i, hb, results) for i, t in tokens]

    async def main() -> None:
        sem = asyncio.Semaphore(50)

        async def boot(s: Screen) -> None:
            async with sem:
                await s.boot()
        await asyncio.gather(*(boot(s) for s in screens))
        tasks = []
        for n, s in enumerate(screens):
            tasks.append(asyncio.create_task(s.session(phases, stop_at, connected, gate)))
            if n % 25 == 24:
                await asyncio.sleep(0.05)
        done = await asyncio.gather(*tasks, return_exceptions=True)
        for s, d in zip(screens, done, strict=True):
            if isinstance(d, BaseException):
                s.errors.append(repr(d)[:200])

    asyncio.run(main())
    out.put({"results": results, "errors": [e for s in screens for e in s.errors]})


def trigger(base: str, api: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(f"{base}{path}", method="POST", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {api}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--screens", type=int, default=1000)
    ap.add_argument("--minutes", type=float, default=1.0, help="heartbeat period before the changes")
    ap.add_argument("--heartbeat", type=float, default=10.0, help="seconds between heartbeats (player default)")
    ap.add_argument("--workers", type=int, default=4, help="processes simulating screens")
    ap.add_argument("--production", action="store_true", help="deployed shape (gunicorn, Celery, Redis, PostgreSQL)")
    ap.add_argument("--web-workers", type=int, default=3, help="gunicorn workers (production mode)")
    ap.add_argument("--ws-workers", type=int, default=3, help="WebSocket workers (production mode)")
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="evac-load-"))
    server = Server(tmp, args.production, args.web_workers, args.ws_workers)
    try:
        server.manage("migrate", "--noinput")
        server.manage("evac_seed_demo")
        data = server.py(f"N = {args.screens}\n" + SETUP)
        server.start()
        port = server.http
        base = f"http://127.0.0.1:{port}"
        ctx = mp.get_context("fork")
        manager = ctx.Manager()
        phases = manager.dict()
        connected, gate_flag = ctx.Value("i", 0), ctx.Value("b", 0)
        out = ctx.Queue()
        stop_at = time.monotonic() + 120 + args.minutes * 60 + 60
        chunks = [list(enumerate(data["tokens"]))[i::args.workers] for i in range(args.workers)]
        started = time.monotonic()
        procs = [ctx.Process(target=worker, args=(port, server.ws, c, args.heartbeat, phases, stop_at, connected,
                                                  gate_flag, out), daemon=True) for c in chunks]
        for p in procs:
            p.start()
        last = 0.0
        while connected.value < args.screens:
            if time.monotonic() - started > 300 or not any(p.is_alive() for p in procs):
                raise SystemExit(f"only {connected.value}/{args.screens} screens connected\n{server.tail_logs()}")
            if time.monotonic() - last > 15:
                last = time.monotonic()
                print(f"… {connected.value}/{args.screens} connected after {last - started:.0f} s", flush=True)
            time.sleep(0.2)
        fleet = time.monotonic() - started
        print(f"{'PASS' if fleet <= FLEET_BOOT_S else 'FAIL'} {args.screens} screens booted and connected in "
              f"{fleet:.1f} s (target ≤ {FLEET_BOOT_S} s)", flush=True)
        gate_flag.value = 1
        time.sleep(args.minutes * 60)
        t = time.time()
        phases["change"] = t
        trigger(base, data["api"], "/api/v1/events/demo/announcements/", {
            "title": "Load test", "body": "Doors open in 10 minutes", "level": "info", "all_screens": True,
            "send": True})
        print(f"announcement API answered in {(time.time() - t) * 1000:.0f} ms", flush=True)
        time.sleep(8)
        t = time.time()
        phases["alarm"] = t
        res = trigger(base, data["api"], "/api/v1/events/demo/evacuation/trigger/",
                      {"state": "evacuate", "reason": "load test"})
        print(f"alarm API answered in {(time.time() - t) * 1000:.0f} ms ({res.get('result')})", flush=True)
        results: dict[str, list[float]] = {}
        errors: list[str] = []
        for _p in procs:
            part = out.get(timeout=stop_at - time.monotonic() + 120)
            for k, v in part["results"].items():
                results.setdefault(k, []).extend(v)
            errors += part["errors"]
        for p in procs:
            p.join(timeout=30)
        failed = int(fleet > FLEET_BOOT_S)
        for step, target in TARGETS_MS.items():
            got = results.get(step, [])
            expected = args.screens if step != "heartbeat" else args.screens * max(1, int(args.minutes * 60 //
                                                                                         args.heartbeat))
            ok = len(got) >= expected * (1 if step != "heartbeat" else 0.9) and pct(got, 0.95) <= target
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'} {step}: {len(got)} (expected {expected}), p50 {pct(got, 0.5):.0f} ms, "
                  f"p95 {pct(got, 0.95):.0f} ms, max {pct(got, 1.0):.0f} ms (target p95 ≤ {target} ms)",
                  flush=True)
        if errors:
            failed += 1
            print(f"FAIL {len(errors)} errors, e.g. {errors[:3]}")
        print("load test: " + ("FAILED" if failed else "passed"))
        if failed:
            print(server.tail_logs(40))
        return 1 if failed else 0
    except BaseException:
        print(server.tail_logs(60), flush=True)
        raise
    finally:
        server.stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
