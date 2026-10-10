# SPDX-License-Identifier: AGPL-3.0-or-later
"""Central's endpoints for venue nodes, ``/api/v1/node/`` (ADR-0002, ADR-0036).

Every request but enrolment carries ``Authorization: Node evacn_…`` and an Ed25519 signature of method, path,
timestamp and body hash (``X-EVAC-Node-Timestamp``, ``X-EVAC-Node-Signature``) made with the node's key; requests
older than five minutes are refused. Only outbound HTTPS from the venue is needed: the node asks, central answers.
"""
from __future__ import annotations

import functools
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core import audit

from . import central, keys, snapshot
from .models import Checkout, Node

View = Callable[..., HttpResponse]


def _body(request: HttpRequest) -> dict[str, Any]:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def node_auth(view: View) -> View:
    @functools.wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        header = request.headers.get("Authorization", "")
        token = header.split(" ", 1)[1].strip() if header.startswith("Node ") else ""
        node = central.authenticate(token)
        if node is None or not keys.verify_request(
                node.sign_public, request.method or "GET", request.get_full_path(), request.body,
                request.headers.get("X-EVAC-Node-Timestamp", ""), request.headers.get("X-EVAC-Node-Signature", "")):
            return JsonResponse({"error": "unknown node or bad signature"}, status=401)
        Node.objects.filter(pk=node.pk).update(last_seen=timezone.now(), last_ip=audit.client_ip(request),
                                               version=request.headers.get("X-EVAC-Version", node.version)[:40])
        request.evac_node = node
        return view(request, *args, **kwargs)

    return csrf_exempt(wrapped)


def _checkout(request: HttpRequest, event_id: Any) -> Checkout:
    co = central.open_checkouts(request.evac_node).filter(event_id=event_id).first()
    if co is None:
        raise Http404("not checked out to this node")
    return co


@csrf_exempt
@require_POST
def enrol(request: HttpRequest) -> JsonResponse:
    data = _body(request)
    try:
        node, token = central.enrol(str(data.get("code", "")), sign_public=str(data.get("sign_public", "")),
                                    box_public=str(data.get("box_public", "")), version=str(data.get("version", "")),
                                    ip=audit.client_ip(request))
    except central.SyncError as err:
        return JsonResponse({"error": str(err)}, status=400)
    return JsonResponse({"node_id": str(node.pk), "name": node.name, "token": token})


@node_auth
@require_GET
def events(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"node": request.evac_node.name, "events": [
        {"event_id": str(co.event_id), "checkout_id": str(co.pk), "slug": co.event.slug, "state": co.state,
         "applied_seq": co.applied_seq,
         "snapshot_version": co.snapshot_version, "seeded": co.seeded}
        for co in central.open_checkouts(request.evac_node)]})


@node_auth
@require_GET
def snapshot_view(request: HttpRequest, event_id: Any) -> HttpResponse:
    co = _checkout(request, event_id)
    data = central.snapshot_for(co)
    etag = f'"{data["version"]}"'
    if request.headers.get("If-None-Match") == etag and co.seeded:
        resp = HttpResponse(status=304)
    else:
        resp = JsonResponse(data)
    resp["ETag"] = etag
    return resp


@node_auth
@require_POST
def snapshot_confirm(request: HttpRequest, event_id: Any) -> JsonResponse:
    co = _checkout(request, event_id)
    data = _body(request)
    central.confirm_snapshot(co, str(data.get("version", "")), seeded=bool(data.get("seeded")))
    return JsonResponse({"ok": True})


RANGE = re.compile(r"^bytes=(\d+)-$")


@node_auth
@require_GET
def file_view(request: HttpRequest, event_id: Any, path: str) -> HttpResponse:
    """A media file the event's snapshot lists; ``Range: bytes=N-`` resumes a download."""
    co = _checkout(request, event_id)
    if path not in {p for p, _sha in snapshot.files_of(co.event, live=True)}:
        raise Http404
    full = (Path(settings.MEDIA_ROOT) / path).resolve()
    if not str(full).startswith(str(Path(settings.MEDIA_ROOT).resolve())) or not full.is_file():
        raise Http404
    size = full.stat().st_size
    m = RANGE.match(request.headers.get("Range", ""))
    start = int(m.group(1)) if m else 0
    if start >= size and size:
        resp = HttpResponse(status=416)
        resp["Content-Range"] = f"bytes */{size}"
        return resp
    fh = full.open("rb")
    fh.seek(start)
    resp = FileResponse(fh, status=206 if m else 200, content_type="application/octet-stream")
    resp["Content-Length"] = str(size - start)
    resp["Accept-Ranges"] = "bytes"
    if m:
        resp["Content-Range"] = f"bytes {start}-{size - 1}/{size}"
    return resp


@node_auth
@require_POST
def oplog(request: HttpRequest, event_id: Any) -> JsonResponse:
    co = _checkout(request, event_id)
    entries = _body(request).get("entries") or []
    if not isinstance(entries, list) or len(entries) > 1000:
        return JsonResponse({"error": "entries must be a list of at most 1000"}, status=400)
    try:
        applied = central.apply_oplog(co, [e for e in entries if isinstance(e, dict)])
    except (central.SyncError, KeyError, ValueError, TypeError) as err:
        return JsonResponse({"error": str(err), "applied_seq": co.applied_seq}, status=422)
    return JsonResponse({"applied_seq": applied})


@node_auth
@require_GET
def actions(request: HttpRequest, event_id: Any) -> JsonResponse:
    co = _checkout(request, event_id)
    try:
        after = int(request.GET.get("after", "0"))
    except ValueError:
        after = 0
    return JsonResponse({"checkin_requested": co.state == Checkout.State.CHECKIN_REQUESTED, "actions": [
        {"id": a.pk, "kind": a.kind, "payload": a.payload, "actor": str(a.actor_id) if a.actor_id else None,
         "actor_repr": a.actor_repr} for a in central.pending_actions(co, after)]})


@node_auth
@require_POST
def action_result(request: HttpRequest, event_id: Any, action_id: int) -> JsonResponse:
    co = _checkout(request, event_id)
    data = _body(request)
    result = data.get("result")
    central.action_done(co, action_id, ok=bool(data.get("ok")), result=result if isinstance(result, dict) else {})
    return JsonResponse({"ok": True})


@node_auth
@require_http_methods(["POST"])
def checkin(request: HttpRequest, event_id: Any) -> JsonResponse:
    co = _checkout(request, event_id)
    data = _body(request)
    try:
        central.complete_checkin(co, final_seq=int(data.get("final_seq", 0)), alarm_seq=int(data.get("alarm_seq", 0)))
    except (central.SyncError, ValueError, TypeError) as err:
        return JsonResponse({"error": str(err), "applied_seq": co.applied_seq}, status=409)
    return JsonResponse({"state": co.state, "applied_seq": co.applied_seq})
