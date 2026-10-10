# SPDX-License-Identifier: AGPL-3.0-or-later
"""The node side of central/node sync (ADR-0002, ADR-0036). Runs as ``manage.py evac_node run``.

Every round, for each event central has checked out to this node:

1. push the op-log (live changes made here) until central confirms it;
2. fetch the snapshot when it changed (``If-None-Match``; every ``SNAPSHOT_EVERY`` seconds) and apply it;
3. download missing media files, resuming partial downloads (``Range``) and checking SHA-256;
4. run live actions central forwarded (alarms raised in the central control room);
5. when central asked for the check-in: push everything, hand back the alarm counter, become a read-only copy.

Only outbound HTTPS is used. Central unreachable: everything keeps working here; the next round catches up.
"""
from __future__ import annotations

import hashlib
import json
import logging
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings
from django.utils import timezone

from apps.core import crypto

from . import keys, snapshot
from .models import NodeEvent, NodeIdentity, OpLogEntry

log = logging.getLogger("evac.node")
API = "/api/v1/node/"
SNAPSHOT_EVERY = 30.0
BATCH = 500
#: at most this many bytes of media per round (the rest follows in the next rounds)
FILE_BUDGET = 64 * 1024 * 1024


class Unreachable(Exception):
    pass


class Response(Protocol):
    status: int
    headers: dict[str, str]
    body: bytes


class Resp:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status, self.headers, self.body = status, headers, body

    def json(self) -> Any:
        return json.loads(self.body or b"{}")


class Transport(Protocol):
    def request(self, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> Resp: ...


class HttpTransport:
    """Signed HTTPS requests to central (``path`` below ``/api/v1/node/``)."""

    def __init__(self, ident: NodeIdentity, timeout: float = 15.0) -> None:
        self.base = ident.central_url.rstrip("/")
        self.token = crypto.decrypt(ident.token_encrypted) if ident.token_encrypted else ""
        self.sign = crypto.decrypt(ident.sign_private_encrypted) if ident.sign_private_encrypted else ""
        self.timeout = timeout
        self.ctx = ssl.create_default_context(cafile=ident.ca_file or None) if self.base.startswith("https") else None

    def request(self, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None) -> Resp:
        full = API + path
        hdrs = {"Authorization": f"Node {self.token}", "Content-Type": "application/json",
                "X-EVAC-Version": __import__("evac").__version__, **(headers or {})}
        if self.sign:
            hdrs.update(keys.sign_request(self.sign, method, full, body))
        req = urllib.request.Request(self.base + full, data=body if method != "GET" else None, method=method,
                                     headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:  # noqa: S310
                return Resp(r.status, dict(r.headers.items()), r.read())
        except urllib.error.HTTPError as err:
            return Resp(err.code, dict(err.headers.items()) if err.headers else {}, err.read() or b"")
        except (urllib.error.URLError, OSError, TimeoutError) as err:
            raise Unreachable(str(err)) from err


def identity() -> NodeIdentity | None:
    ident = NodeIdentity.objects.filter(pk=1).first()
    return ident if ident is not None and ident.enrolled_at else None


def enrol(central_url: str, code: str, *, ca_file: str = "", transport: Transport | None = None) -> NodeIdentity:
    """Create this node's keys, present them with the one-time code and keep the token."""
    pair = keys.generate()
    ident = NodeIdentity(pk=1, central_url=central_url.rstrip("/"), ca_file=ca_file)
    t = transport or HttpTransport(ident)
    body = json.dumps({"code": code, "sign_public": pair["sign_public"], "box_public": pair["box_public"],
                       "version": __import__("evac").__version__}).encode()
    resp = t.request("POST", "enrol/", body)
    if resp.status != 200:
        raise ValueError(_error(resp))
    data = resp.json()
    ident.node_id, ident.name = data["node_id"], data["name"]
    ident.sign_private_encrypted = crypto.encrypt(pair["sign_private"])
    ident.box_private_encrypted = crypto.encrypt(pair["box_private"])
    ident.sign_public, ident.box_public = pair["sign_public"], pair["box_public"]
    ident.token_encrypted = crypto.encrypt(data["token"])
    ident.enrolled_at = ident.last_contact = timezone.now()
    ident.save()
    return ident


def _error(resp: Resp) -> str:
    try:
        return str(resp.json().get("error") or resp.status)
    except ValueError:
        return f"HTTP {resp.status}"


def _post(t: Transport, path: str, data: dict[str, Any]) -> Resp:
    return t.request("POST", path, json.dumps(data, default=str).encode())


# --------------------------------------------------------------------------------------------- one round
def sync_once(transport: Transport | None = None, *, snapshots: bool = True) -> dict[str, Any]:
    ident = identity()
    if ident is None:
        raise ValueError("this node is not enrolled (manage.py evac_node enrol)")
    t = transport or HttpTransport(ident)
    summary: dict[str, Any] = {"events": []}
    try:
        resp = t.request("GET", "events/")
        if resp.status != 200:
            raise Unreachable(_error(resp))
        listed = {e["event_id"]: e for e in resp.json().get("events", [])}
        held = {str(n.event_id): n for n in NodeEvent.objects.filter(checked_out=True)}
        for event_id, info in listed.items():
            ne = held.get(event_id)
            if ne is None or str(ne.checkout_id) != info.get("checkout_id"):
                # a new checkout: start over (seed, numbering)
                ne = NodeEvent.objects.update_or_create(event_id=event_id, defaults={
                    "slug": info["slug"], "checked_out": True, "checkout_id": info.get("checkout_id"),
                    "seeded": False, "snapshot_version": "", "snapshot_at": None, "next_seq": 1, "pushed_seq": 0,
                    "action_after": 0})[0]
            summary["events"].append(sync_event(t, ne, info, snapshots=snapshots))
        for event_id, ne in held.items():
            if event_id not in listed:  # central took it back (forced check-in)
                ne.checked_out = False
                ne.save(update_fields=["checked_out"])
                log.warning("event %s is no longer checked out to this node", ne.slug)
        NodeIdentity.objects.filter(pk=1).update(last_contact=timezone.now(), last_error="")
    except Unreachable as err:
        NodeIdentity.objects.filter(pk=1).update(last_error=f"central unreachable: {err}"[:300])
        summary["error"] = str(err)
    return summary


def sync_event(t: Transport, ne: NodeEvent, info: dict[str, Any], *, snapshots: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {"event": ne.slug}
    if ne.seeded:
        out["pushed"] = push_oplog(t, ne)
    due = not ne.snapshot_at or (timezone.now() - ne.snapshot_at).total_seconds() >= SNAPSHOT_EVERY
    if snapshots and (due or not ne.seeded):
        out["snapshot"] = pull_snapshot(t, ne)
        out["files"] = fetch_files(t, ne)
    if ne.seeded:
        out["actions"] = run_actions(t, ne)
        if out["actions"]:
            push_oplog(t, ne)
        if info.get("state") == "checkin_requested":
            out["checkin"] = checkin(t, ne)
    return out


def push_oplog(t: Transport, ne: NodeEvent) -> int:
    sent = 0
    while True:
        batch = list(OpLogEntry.objects.filter(event_id=ne.event_id, pushed_at__isnull=True).order_by("seq")[:BATCH])
        if not batch:
            return sent
        resp = _post(t, f"events/{ne.event_id}/oplog/", {"entries": [
            {"seq": e.seq, "key": e.key, "kind": e.kind, "model": e.model, "object_id": e.object_id, "data": e.data,
             "created_at": e.created_at.isoformat()} for e in batch]})
        if resp.status != 200:
            raise Unreachable(f"op-log refused: {_error(resp)}")
        applied = int(resp.json().get("applied_seq", 0))
        done = OpLogEntry.objects.filter(event_id=ne.event_id, pushed_at__isnull=True, seq__lte=applied).update(
            pushed_at=timezone.now())
        NodeEvent.objects.filter(pk=ne.pk).update(pushed_seq=applied)
        ne.pushed_seq = applied
        sent += done
        if done < len(batch):
            return sent  # central stopped at a gap or an error; the next round retries


def pull_snapshot(t: Transport, ne: NodeEvent) -> str:
    headers = {"If-None-Match": f'"{ne.snapshot_version}"'} if ne.seeded and ne.snapshot_version else {}
    resp = t.request("GET", f"events/{ne.event_id}/snapshot/", headers=headers)
    ne.snapshot_at = timezone.now()
    if resp.status == 304:
        ne.save(update_fields=["snapshot_at"])
        return "unchanged"
    if resp.status != 200:
        raise Unreachable(f"snapshot: {_error(resp)}")
    data = resp.json()
    ident = identity()
    box = crypto.decrypt(ident.box_private_encrypted) if ident and ident.box_private_encrypted else ""
    event = snapshot.apply(data, box_private=box)
    ne.snapshot_version, ne.seeded, ne.files = data["version"], True, data.get("files", [])
    ne.files_missing = len(snapshot.missing_files(data))
    ne.save()
    _post(t, f"events/{ne.event_id}/snapshot/confirm/", {"version": data["version"], "seeded": bool(data.get("seed"))})
    _after_snapshot(event)
    log.info("applied snapshot %s of %s", data["version"], ne.slug)
    return "applied"


def _after_snapshot(event: Any) -> None:
    """Configuration changed under running screens: tell them (alarm payloads are re-signed and pushed)."""
    from django.apps import apps

    if apps.is_installed("apps.evacuation"):
        from apps.evacuation import feed

        feed.push(event)


def fetch_files(t: Transport, ne: NodeEvent, budget: int = FILE_BUDGET) -> int:
    root = Path(settings.MEDIA_ROOT)
    fetched = 0
    missing = [(p, s) for p, s in ne.files if not (root / p).exists()]
    for path, sha in missing:
        if budget <= 0:
            break
        dest = (root / path).resolve()
        if not str(dest).startswith(str(root.resolve())):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        start = part.stat().st_size if part.exists() else 0
        resp = t.request("GET", f"events/{ne.event_id}/files/{urllib.parse.quote(path)}",
                         headers={"Range": f"bytes={start}-"} if start else {})
        if resp.status == 416:  # complete already
            pass
        elif resp.status not in (200, 206):
            log.warning("file %s: HTTP %s", path, resp.status)
            continue
        else:
            with part.open("ab" if resp.status == 206 else "wb") as fh:
                fh.write(resp.body)
            budget -= len(resp.body)
        if sha and hashlib.sha256(part.read_bytes()).hexdigest() != sha:
            log.warning("file %s: checksum mismatch, fetching again", path)
            part.unlink(missing_ok=True)
            continue
        part.replace(dest)
        fetched += 1
    NodeEvent.objects.filter(pk=ne.pk).update(files_missing=len(missing) - fetched)
    return fetched


def run_actions(t: Transport, ne: NodeEvent) -> int:
    from django.apps import apps as django_apps
    from django.conf import settings as django_settings

    from apps.core.registry import registry

    resp = t.request("GET", f"events/{ne.event_id}/actions/?after={ne.action_after}")
    if resp.status != 200:
        return 0
    event = django_apps.get_model("events", "Event").objects.filter(pk=ne.event_id).first()
    user_model = django_apps.get_model(django_settings.AUTH_USER_MODEL)
    done = 0
    for a in resp.json().get("actions", []):
        fn = registry.ensure_loaded().node_actions.get(a["kind"])
        actor = user_model.objects.filter(pk=a.get("actor")).first() if a.get("actor") else None
        try:
            if fn is None or event is None:
                raise ValueError(f"unknown action {a['kind']}")
            ok, result = True, dict(fn(event, a.get("payload") or {}, actor))
        except Exception as err:  # noqa: BLE001 - every outcome goes back to central
            ok, result = False, {"error": str(getattr(err, "message", err))[:300]}
        _post(t, f"events/{ne.event_id}/actions/{a['id']}/", {"ok": ok, "result": result})
        NodeEvent.objects.filter(pk=ne.pk).update(action_after=a["id"])
        ne.action_after = a["id"]
        done += 1
    return done


def checkin(t: Transport, ne: NodeEvent) -> str:
    push_oplog(t, ne)
    if OpLogEntry.objects.filter(event_id=ne.event_id, pushed_at__isnull=True).exists():
        return "pending"
    alarm_seq = 0
    from django.apps import apps as django_apps

    if django_apps.is_installed("apps.evacuation"):
        from apps.evacuation import feed

        event = django_apps.get_model("events", "Event").objects.filter(pk=ne.event_id).first()
        alarm_seq = feed.current_seq(event) if event else 0
    resp = _post(t, f"events/{ne.event_id}/checkin/", {"final_seq": ne.next_seq - 1, "alarm_seq": alarm_seq})
    if resp.status != 200:
        return f"refused: {_error(resp)}"
    ne.checked_out = False
    ne.save(update_fields=["checked_out"])
    log.info("event %s checked in", ne.slug)
    return "checked_in"


def run(interval: float = 2.0, rounds: int = 0) -> None:  # pragma: no cover - long-running loop
    """Sync forever (or ``rounds`` times): op-log and actions every ``interval``, snapshots every 30 s."""
    n = 0
    while rounds == 0 or n < rounds:
        try:
            summary = sync_once()
            if summary.get("error"):
                log.warning("central unreachable: %s", summary["error"])
        except Exception:
            log.exception("sync round failed")
        n += 1
        time.sleep(interval)
