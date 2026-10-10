# SPDX-License-Identifier: AGPL-3.0-or-later
"""The link to a DIAL event (roadmap 4.1): settings schema, the configuration of an EVAC event, test connection."""
from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

from apps.core.plugins import ConnectionResult

from .client import Client, DialError, Rejected

KEY = "dial"
#: token scopes the link needs (documented on the settings page and in docs/extensions/dial.md)
SCOPES = ("events:read", "pages:read", "phonebook:read", "dect:read", "ivr:read", "emergency:read", "emergency:write",
          "messaging:write")

STAGES = ["staff_alert", "attention", "shelter_in_place", "evacuate"]
STAGE_LABELS = ["Staff alert", "Attention", "Shelter in place", "Evacuate"]

SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["base_url", "event"],
    "properties": {
        "base_url": {"type": "string", "format": "uri", "title": "DIAL URL", "maxLength": 300,
                     "description": "e.g. https://dial.example.org"},
        "event": {"type": "string", "title": "DIAL event slug", "maxLength": 80, "pattern": "^[A-Za-z0-9_-]+$"},
        "verify_tls": {"type": "boolean", "title": "Verify TLS certificates", "default": True},
        "timeout_seconds": {"type": "integer", "title": "Timeout (seconds)", "minimum": 2, "maximum": 30,
                            "default": 10},
        "emergency_stage": {"type": "string", "title": "Alarm stage for an emergency call in DIAL",
                            "enum": STAGES, "x-enum-labels": STAGE_LABELS, "default": "staff_alert",
                            "description": "What the evacuation trigger asks for when someone dials an emergency "
                                           "number in DIAL. The trigger policy (Evacuation → Triggers) decides "
                                           "whether it executes, waits for the control room or only notifies."},
        "emergency_numbers": {"type": "string", "title": "Only these emergency numbers", "maxLength": 200,
                              "description": "Comma-separated; empty = every emergency number of the DIAL event."},
        "broadcast_states": {"type": "array", "title": "Ring DIAL handsets for these stages",
                             "items": {"type": "string", "enum": STAGES, "x-enum-labels": STAGE_LABELS},
                             "default": ["attention", "shelter_in_place", "evacuate"],
                             "uniqueItems": True},
        "broadcast_all_clear": {"type": "boolean", "title": "Also announce the all clear on DIAL handsets",
                                "default": True},
        "broadcast_drills": {"type": "boolean", "title": "Ring DIAL handsets for drills too", "default": False},
        "broadcast_group": {"type": "string", "title": "DIAL group to ring (slug)", "maxLength": 80,
                            "description": "Empty = every active handset of the DIAL event."},
        "important_numbers": {"type": "string", "title": "Important numbers", "maxLength": 2000,
                              "x-widget": "textarea",
                              "description": "One per line: number = what for (e.g. 1100 = Info desk). Shown first "
                                             "in the “call X for Y” widget, before DIAL's emergency and service "
                                             "numbers."},
        "auto_publish_extensions": {"type": "string", "title": "Publish phone recordings at once from these "
                                                                "extensions", "maxLength": 300,
                                    "description": "Comma-separated DIAL extension numbers. Recordings from other "
                                                   "extensions wait in the approval queue."},
        "recording_level": {"type": "string", "title": "Announcement level for phone recordings", "maxLength": 40,
                            "default": "info"},
        "transcribe": {"type": "boolean", "title": "Transcribe phone recordings (offline Whisper, English)",
                       "default": True},
    },
}


def settings_of(config: Any) -> dict[str, Any]:
    out = {k: v.get("default") for k, v in SCHEMA["properties"].items() if "default" in v}
    out.update({k: v for k, v in (config.settings or {}).items() if v is not None})
    return out


def csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value or "").replace(";", ",").split(",") if v.strip()]


def missing_scopes(granted: list[str]) -> list[str]:
    """Scopes the link uses that the token does not grant (DIAL: empty list or ``*`` = all, ``<app>:*`` = the app)."""
    granted = [str(g) for g in granted]
    if not granted or "*" in granted:
        return []
    return [s for s in SCOPES if s not in granted and f"{s.split(':')[0]}:*" not in granted]


def test_connection(config: Any) -> ConnectionResult:
    """DIAL ``GET /api/v1/health/?event=<slug>`` (no token needed) and ``GET /api/v1/me/`` (the token)."""
    client = Client.for_config(config)
    if not client.event:
        return ConnectionResult(False, _("Set the DIAL event slug."))
    try:
        status, health = client.request("GET", "health/", params={"event": client.event}, accept=(404, 503))
        if status == 404:
            return ConnectionResult(False, _("DIAL does not know the event “%(e)s”.") % {"e": client.event})
        if not client.token:
            return ConnectionResult(False, _("DIAL answers, but no service token is set."))
        me = client.get("me/")
    except Rejected as exc:
        if exc.status in (401, 403):
            return ConnectionResult(False, _("DIAL refused the service token (%(s)s).") % {"s": exc.status})
        return ConnectionResult(False, str(exc))
    except DialError as exc:
        return ConnectionResult(False, str(exc))
    health = health if isinstance(health, dict) else {}
    me = me if isinstance(me, dict) else {}
    who = me.get("service_account") or me.get("display_name") or me.get("username") or "?"
    parts = [_("Connected to DIAL as %(who)s.") % {"who": who}]
    for name, label in (("pbx", _("PBX")), ("dect", _("DECT"))):
        part = health.get(name) or {}
        if isinstance(part, dict) and part:
            parts.append(f"{label}: " + (_("ok") if part.get("ok") else str(part.get("error") or _("problem"))))
    token = me.get("token") if isinstance(me.get("token"), dict) else None
    if token is not None:
        missing = missing_scopes(token.get("scopes") or [])
        if missing:
            parts.append(_("The token lacks: %(s)s.") % {"s": " ".join(missing)})
        if token.get("event") and token["event"] != client.event:
            parts.append(_("The token is bound to the DIAL event “%(e)s”.") % {"e": token["event"]})
    ok = status == 200 or status == 503  # 503: DIAL is up, a venue backend is not
    return ConnectionResult(ok, " ".join(parts), {"health": health, "me": {k: me.get(k) for k in
                                                                           ("username", "service_account")}})
