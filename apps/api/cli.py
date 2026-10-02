# SPDX-License-Identifier: AGPL-3.0-or-later
"""``evac`` - command-line client for the EVAC REST API.

Configuration: ``--url`` / ``EVAC_URL`` (default http://localhost:8000) and ``--token`` / ``EVAC_TOKEN``
(a service token, ``evac_...``). Output is JSON (``--json``) or short human-readable text.

    evac health
    evac whoami
    evac events list
    evac events show demo
    evac events export demo -o demo.json
    evac events import demo.json --slug demo-copy
    evac events transition demo live
    evac modules demo
    evac modules demo --set venues=off
    evac audit demo --limit 20
    evac audit-verify
    evac tokens list

Plugins add sub-commands through ``registry.cli_command`` (e.g. ``evac drill`` in the evacuation phase);
those are available when the CLI runs inside an EVAC installation (Django importable).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


class Client:
    def __init__(self, url: str, token: str, timeout: float = 15):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.session.headers["Accept"] = "application/json"
        self.timeout = timeout

    def request(self, method: str, path: str, **kwargs) -> Any:
        r = self.session.request(method, f"{self.url}/api/v1/{path.lstrip('/')}", timeout=self.timeout, **kwargs)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except ValueError:
                detail = r.text[:300]
            raise SystemExit(f"error: HTTP {r.status_code}: {detail}")
        return r.json() if r.content else None

    def get(self, path: str, **params) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, data: Any) -> Any:
        return self.request("POST", path, json=data)

    def patch(self, path: str, data: Any) -> Any:
        return self.request("PATCH", path, json=data)


def _out(args, data: Any, text: str | None = None) -> None:
    if args.json or text is None:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(text)


def _results(data: Any) -> list:
    return data["results"] if isinstance(data, dict) and "results" in data else data


def cmd_health(args, c: Client) -> int:
    d = c.get("health/")
    _out(args, d, f"{d['status']} - EVAC {d['version']} ({d['mode']})")
    return 0


def cmd_whoami(args, c: Client) -> int:
    d = c.get("me/")
    events = ", ".join(e["slug"] for e in d.get("events", [])) or "-"
    _out(args, d, f"{d['email']}{' (instance admin)' if d['is_superuser'] else ''} - events: {events}")
    return 0


def cmd_events(args, c: Client) -> int:
    if args.action == "list":
        rows = _results(c.get("events/", limit=500))
        _out(args, rows, "\n".join(f"{e['slug']:<24} {e['state']:<9} {e['name']}" for e in rows) or "(none)")
    elif args.action == "show":
        _out(args, c.get(f"events/{args.slug}/"))
    elif args.action == "export":
        data = c.get(f"events/{args.slug}/export/")
        if args.output and args.output != "-":
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"written {args.output}")
        else:
            print(json.dumps(data, indent=2))
    elif args.action == "import":
        with open(args.slug, encoding="utf-8") as fh:
            data = json.load(fh)
        d = c.post("events/import/", {"data": data, "slug": args.new_slug or ""})
        _out(args, d, f"imported as {d['slug']}" + "".join(f"\n  ! {line}" for line in d.get("report", [])))
    elif args.action == "transition":
        if not args.state:
            raise SystemExit("error: give the target state")
        d = c.post(f"events/{args.slug}/transition/", {"state": args.state})
        _out(args, d, f"{d['slug']} is now {d['state']}")
    return 0


def cmd_modules(args, c: Client) -> int:
    for item in args.set or []:
        key, _, value = item.partition("=")
        enabled = {"on": True, "off": False, "inherit": None}.get(value)
        if value not in ("on", "off", "inherit"):
            raise SystemExit("error: use --set <module>=on|off|inherit")
        c.patch(f"events/{args.slug}/modules/{key}/", {"event": enabled})
    rows = c.get(f"events/{args.slug}/modules/")
    _out(args, rows, "\n".join(f"{r['key']:<16} {'active' if r['active'] else 'inactive':<9} {r['name']}"
                               for r in rows))
    return 0


def cmd_audit(args, c: Client) -> int:
    rows = _results(c.get(f"events/{args.slug}/audit/", limit=args.limit))
    _out(args, rows, "\n".join(f"{r['created_at'][:19]} {r['actor_repr'] or 'system':<30} {r['action']:<28} "
                               f"{r['message']}" for r in rows) or "(none)")
    return 0


def cmd_audit_verify(args, c: Client) -> int:
    d = c.get("audit/verify/")
    _out(args, d, f"audit chain {'OK' if d['ok'] else 'BROKEN at ' + str(d['first_bad_id']) + ': ' + d['reason']} "
                  f"({d['checked']} rows)")
    return 0 if d["ok"] else 1


def cmd_tokens(args, c: Client) -> int:
    rows = _results(c.get("tokens/"))
    _out(args, rows, "\n".join(f"{t['token_prefix']}…  {t['name']:<24} {' '.join(t['scopes']) or 'all'}"
                               for t in rows) or "(none)")
    return 0


def _plugin_commands() -> list:
    try:
        import django

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "evac.settings.prod")
        django.setup()
        from apps.core.registry import registry

        return list(registry.ensure_loaded().cli_commands.values())
    except Exception:  # noqa: BLE001 - the CLI also runs outside an installation
        return []


def build_parser(plugin_cmds=()) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="evac", description="EVAC command-line client")
    p.add_argument("--url", default=os.environ.get("EVAC_URL", "http://localhost:8000"))
    p.add_argument("--token", default=os.environ.get("EVAC_TOKEN", ""))
    p.add_argument("--json", action="store_true", help="print raw JSON")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="server status").set_defaults(fn=cmd_health)
    sub.add_parser("whoami", help="who the token belongs to").set_defaults(fn=cmd_whoami)
    ev = sub.add_parser("events", help="list/show/export/import/transition events")
    ev.add_argument("action", choices=["list", "show", "export", "import", "transition"])
    ev.add_argument("slug", nargs="?", default="", help="event slug (or file for import)")
    ev.add_argument("state", nargs="?", default="", help="target state for transition")
    ev.add_argument("-o", "--output", default="-")
    ev.add_argument("--new-slug", default="")
    ev.set_defaults(fn=cmd_events)
    mo = sub.add_parser("modules", help="show or switch an event's modules")
    mo.add_argument("slug")
    mo.add_argument("--set", action="append", help="<module>=on|off|inherit")
    mo.set_defaults(fn=cmd_modules)
    au = sub.add_parser("audit", help="recent audit entries of an event")
    au.add_argument("slug")
    au.add_argument("--limit", type=int, default=50)
    au.set_defaults(fn=cmd_audit)
    sub.add_parser("audit-verify", help="verify the audit hash chain (instance admin)").set_defaults(
        fn=cmd_audit_verify)
    sub.add_parser("tokens", help="your service tokens").set_defaults(fn=cmd_tokens)
    for spec in plugin_cmds:
        sp = sub.add_parser(spec.name, help=spec.help)
        spec.configure(sp)
        sp.set_defaults(fn=spec.run)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    builtin = {"health", "whoami", "events", "modules", "audit", "audit-verify", "tokens", "-h", "--help"}
    plugin_cmds = [] if (argv and argv[0] in builtin) else _plugin_commands()
    args = build_parser(plugin_cmds).parse_args(argv)
    return int(args.fn(args, Client(args.url, args.token)) or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
