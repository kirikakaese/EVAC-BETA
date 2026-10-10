# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTPS endpoints for hardware bridges (ADR-0032): ``/bridge/v1/heartbeat`` and ``/bridge/v1/input``.

Authentication: ``Authorization: Bearer evacb_...`` (the bridge's own token, shown once when it is added).
Bridges are not people: they never end alarms and get no session, cookies or CSRF.
"""
from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.core import audit, modules

from . import bridges


def _auth(request: HttpRequest) -> tuple[Any, dict[str, Any] | None, JsonResponse | None]:
    header = request.headers.get("Authorization", "")
    raw = header.split(" ", 1)[1].strip() if header.lower().startswith("bearer ") else ""
    bridge = bridges.authenticate(raw)
    if bridge is None:
        return None, None, JsonResponse({"error": "unknown bridge token"}, status=401)
    if not modules.is_enabled("evacuation", bridge.event):
        return None, None, JsonResponse({"error": "the evacuation module is off for this event"}, status=409)
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return None, None, JsonResponse({"error": "body must be JSON"}, status=400)
    if not isinstance(body, dict):
        return None, None, JsonResponse({"error": "body must be a JSON object"}, status=400)
    return bridge, body, None


@csrf_exempt
@require_POST
def heartbeat(request: HttpRequest) -> JsonResponse:
    bridge, body, err = _auth(request)
    if err is not None:
        return err
    assert body is not None
    raw_inputs, raw_info = body.get("inputs"), body.get("info")
    inputs: dict[str, Any] = raw_inputs if isinstance(raw_inputs, dict) else {}
    info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
    cfg = bridges.heartbeat(bridge, inputs={str(k): str(v) for k, v in inputs.items()}, info=info,
                            ip=audit.client_ip(request))
    return JsonResponse(cfg)


@csrf_exempt
@require_POST
def input_changed(request: HttpRequest) -> JsonResponse:
    bridge, body, err = _auth(request)
    if err is not None:
        return err
    assert body is not None
    key, state = str(body.get("input", "")), str(body.get("state", ""))
    res = bridges.report(bridge, key, state, event_key=str(body.get("id", ""))[:60])
    status = 404 if res.result == "unknown_input" else 400 if res.result == "bad_state" else 200
    return JsonResponse({"result": res.result, "request": res.request, "detail": res.detail}, status=status)
