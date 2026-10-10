#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fallback origin for the chaos tests (ADR-0034), built from the reference bridge's ``FallbackState``.

It relays EVAC's signed state (``/evac/<event>/state``, polled every second) like a secondary node or a bridge, and
takes commands on ``POST /control/<what>`` to misbehave on purpose:

- ``issue``: sign an alarm itself (as a bridge does when EVAC is unreachable; needs the exported alarm key);
- ``forge``: serve a message signed with some other key;
- ``stale-clear``: serve an all clear signed with the right key but issued an hour ago;
- ``bridge-clear``: serve an all clear signed with the right key but marked as issued by a bridge;
- ``relay``: back to relaying EVAC.

    python scripts/chaos_fallback.py --port 8766 --central http://127.0.0.1:8765 --event demo --key <base64url>
"""
from __future__ import annotations

import argparse
import http.server
import importlib.util
import json
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

spec = importlib.util.spec_from_file_location("evac_bridge", Path(__file__).resolve().parents[1] / "bridge" /
                                              "evac_bridge.py")
eb = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["evac_bridge"] = eb
spec.loader.exec_module(eb)  # type: ignore[union-attr]


def signed(seed: bytes, core: dict[str, Any]) -> dict[str, Any]:
    m = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return {"sig": {"kid": "chaos", "m": m, "s": eb.b64(eb.ed25519_sign(seed, m.encode()))}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--central", required=True)
    ap.add_argument("--event", default="demo")
    ap.add_argument("--key", required=True, help="the event's exported alarm key (base64url)")
    args = ap.parse_args()
    seed = eb.unb64(args.key)
    state = eb.FallbackState(None, key=args.key, name="chaos")
    state.config = {"event": args.event, "inputs": [
        {"key": "panel", "state": "evacuate", "zone": "", "policy": {"action": "execute"}}]}
    mode = {"relay": True}

    def poll() -> None:
        while True:
            if mode["relay"]:
                try:
                    with urllib.request.urlopen(f"{args.central}/evac/{args.event}/state", timeout=2) as r:
                        state.update({"state": json.loads(r.read())})
                except OSError:
                    pass  # EVAC is down: keep serving the last state
            time.sleep(1)

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict[str, Any] | None) -> None:
            data = json.dumps(body or {}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path.split("?")[0].rstrip("/") == f"/evac/{args.event}/state" and state.message:
                self._send(200, state.message)
            else:
                self._send(404, {"error": "no state"})

        def do_POST(self) -> None:  # noqa: N802
            what = self.path.rstrip("/").rsplit("/", 1)[-1]
            core = dict(state.core or {"e": args.event, "sc": "*", "seq": 0, "ia": int(time.time()), "z": {}, "b": []})
            seq = int(core.get("seq", 0)) + 1
            clear = {"st": "all_clear", "d": False, "cu": int((time.time() + 600) * 1000)}
            mode["relay"] = what == "relay"
            if what == "issue":
                state.issue("panel")
            elif what == "forge":
                state.message = signed(eb.unb64(eb.b64(b"\x01" * 32)), {**core, "seq": seq + 100, "ev": clear,
                                                                       "ia": int(time.time())})
            elif what == "stale-clear":
                state.message = signed(seed, {**core, "seq": seq, "ev": clear, "z": {}, "ia": int(time.time()) - 3600})
            elif what == "bridge-clear":
                state.message = signed(seed, {**core, "seq": seq, "ev": clear, "z": {}, "ia": int(time.time()),
                                              "is": "bridge:chaos"})
            elif what != "relay":
                self._send(404, {"error": what})
                return
            self._send(200, {"mode": what, "seq": (state.core or {}).get("seq")})

        def log_message(self, fmt: str, *a: Any) -> None:
            pass

    threading.Thread(target=poll, daemon=True).start()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"fallback origin on {args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
