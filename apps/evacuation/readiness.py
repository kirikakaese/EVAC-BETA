# SPDX-License-Identifier: AGPL-3.0-or-later
"""Readiness of the fail-safe (roadmap 3.9, ADR-0034): could every screen show an alarm without the server?

Per screen: online, evacuation bundle loaded and current, sound allowed by the browser, last self-test. The
self-test is sent to the players over their normal channel; each renders every stage off screen (optionally a
visible test frame), checks the signature, the sound permission and the fallback origins, and reports back.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import audit

from . import acks, feed
from .models import ScreenAck

#: a self-test older than this is due again
SELFTEST_MAX_AGE = timedelta(days=7)
#: players fetch the bundle every minute; older than this means the screen is not refreshing it
BUNDLE_MAX_AGE = timedelta(minutes=10)
#: a newly served bundle needs a heartbeat to be reported back
BUNDLE_GRACE = timedelta(minutes=2)


@dataclass
class Row:
    screen: Any
    role: str
    online: bool
    ack: ScreenAck | None
    audio: str
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.problems


def _paired(event: Any) -> list[Any]:
    from django.apps import apps

    if not apps.is_installed("apps.screens"):
        return []
    from apps.screens.models import Screen

    return list(Screen.objects.paired().filter(event=event).order_by("name"))


def _selftest_problems(test: dict[str, Any]) -> list[str]:
    out = [f"{stage}: {result}" for stage, result in (test.get("stages") or {}).items() if result != "ok"]
    if test.get("signature") == "invalid":
        out.append(_("signature does not verify with the bundled keys"))
    out += [f"{origin}: {result}" for origin, result in (test.get("origins") or {}).items() if result != "ok"]
    return out


def screens(event: Any, now: Any = None) -> list[Row]:
    now = now or timezone.now()
    rows = []
    found = acks.screen_acks(event)
    paired = _paired(event)
    role_of = feed.roles(event, paired)
    for s in paired:
        role = role_of[str(s.pk)]
        ack = found.get(str(s.pk))
        reported = s.reported or {}
        audio = str(reported.get("evac_audio") or "")
        row = Row(s, role, s.health_state == "online", ack, audio)
        if role == "excluded":
            rows.append(row)
            continue
        if not row.online:
            row.problems.append(_("offline") if s.health_state != "stale" else _("no recent heartbeat"))
        if ack is None or not ack.bundle_served:
            row.problems.append(_("has not loaded the evacuation bundle"))
        else:
            if (reported.get("evac_bundle") or "") != ack.bundle_served and ack.bundle_served_at \
                    and now - ack.bundle_served_at > BUNDLE_GRACE:
                row.problems.append(_("evacuation bundle not current"))
            if row.online and ack.bundle_served_at and now - ack.bundle_served_at > BUNDLE_MAX_AGE:
                row.warnings.append(_("bundle not refreshed for %(m)s minutes")
                                    % {"m": int((now - ack.bundle_served_at).total_seconds() // 60)})
        if role == "participant":
            if audio == "suspended":
                row.problems.append(_("sound blocked by the browser (autoplay)"))
            elif audio == "unavailable":
                row.warnings.append(_("no sound output"))
        if ack is None or ack.selftest_at is None:
            row.warnings.append(_("never self-tested"))
        else:
            if now - ack.selftest_at > SELFTEST_MAX_AGE:
                row.warnings.append(_("last self-test over 7 days ago"))
            if not (ack.selftest or {}).get("ok"):
                row.problems.append(_("self-test: %(p)s") % {
                    "p": "; ".join(_selftest_problems(ack.selftest or {})) or _("failed")})
        rows.append(row)
    return rows


def summary(rows: list[Row]) -> dict[str, int]:
    counted = [r for r in rows if r.role != "excluded"]
    return {"total": len(counted), "ready": sum(r.ready for r in counted),
            "problems": sum(not r.ready for r in counted), "warnings": sum(bool(r.warnings) for r in counted)}


def run_selftest(event: Any, *, visible: bool = False, seconds: int = 5, actor: Any = None, request: Any = None,
                 screen_ids: list[str] | None = None) -> int:
    """Ask the event's screens (or ``screen_ids``) to self-test. Returns how many were asked."""
    from apps.screens import channel

    targets = [s for s in _paired(event) if screen_ids is None or str(s.pk) in screen_ids]
    seconds = max(2, min(int(seconds or 5), 60))
    for s in targets:
        channel.send(s, "evac.selftest", {"visible": bool(visible), "seconds": seconds})
    audit.log(action="evacuation.selftest", actor=actor, event=event, request=request,
              message=f"self-test sent to {len(targets)} screens" + (" (visible)" if visible else ""))
    return len(targets)
