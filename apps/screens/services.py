# SPDX-License-Identifier: AGPL-3.0-or-later
"""All state changes of screens and screen groups (audit-logged), pairing and device authentication."""
from __future__ import annotations

import datetime as dt
import secrets
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import crypto, settings_store, webhooks
from apps.core.audit import log

from . import channel
from .models import (
    CODE_ALPHABET,
    CODE_LENGTH,
    TOKEN_PREFIX,
    PairingRequest,
    Screen,
    ScreenGroup,
    hash_secret,
    normalize_code,
)

#: keys a player may report in its heartbeat (anything else is dropped), with a max length for strings
REPORTED_KEYS = {
    "version": 40, "resolution": 20, "orientation": 20, "uptime": 0, "slide": 200, "errors": 0, "memory": 0,
    "last_sync": 40, "evac_ack": 40, "online": 0, "user_agent": 300, "content_version": 64,
}


def screen_settings(event) -> dict[str, Any]:
    general = settings_store.get("general", event=event)
    values = settings_store.get("screens", event=event)
    return {"heartbeat_seconds": int(general.get("heartbeat_seconds", 10)), **values}


# --------------------------------------------------------------------------- pairing

def start_pairing(*, ip: str | None = None, user_agent: str = "", info: dict | None = None
                  ) -> tuple[PairingRequest, str]:
    """A player asks to be paired. Returns the request and the secret it polls with (shown only now)."""
    now = timezone.now()
    active = set(PairingRequest.objects.filter(expires_at__gt=now, claimed_at__isnull=True)
                 .values_list("code", flat=True))
    for _attempt in range(20):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if code not in active:
            break
    secret = secrets.token_urlsafe(32)
    req = PairingRequest.objects.create(
        code=code, secret_hash=hash_secret(secret), ip=ip, user_agent=(user_agent or "")[:300],
        info=_clean_reported(info or {}), expires_at=now + dt.timedelta(minutes=PairingRequest.TTL_MINUTES))
    return req, secret


def pending_request(code: str) -> PairingRequest | None:
    code = normalize_code(code)
    if len(code) != CODE_LENGTH:
        return None
    return (PairingRequest.objects.filter(code=code, claimed_at__isnull=True, expires_at__gt=timezone.now())
            .order_by("-created_at").first())


@transaction.atomic
def pair(event, code: str, *, actor, request=None, screen: Screen | None = None, name: str = "",
         venue=None, zone=None, room=None, groups=(), tags=()) -> Screen:
    """Claim the pairing request with ``code`` for a new screen (or re-pair an existing ``screen``)."""
    req = pending_request(code)
    if req is None:
        raise ValidationError(_("No screen is waiting with this code. Check the code on the screen; codes "
                                "expire after %(minutes)d minutes.") % {"minutes": PairingRequest.TTL_MINUTES})
    PairingRequest.objects.select_for_update().filter(pk=req.pk).first()
    repair = screen is not None and not screen._state.adding
    if screen is None:
        screen = Screen(event=event, name=name or _("Screen %(code)s") % {"code": req.display_code})
    if screen.event_id != event.pk:
        raise ValidationError(_("This screen belongs to another event."))
    if not repair:
        screen.venue, screen.zone, screen.room = venue, zone, room
        screen.tags = _clean_tags(tags)
    raw = screen.issue_token()
    screen.paired_at, screen.paired_by = timezone.now(), actor
    screen.last_seen_at, screen.reported = None, dict(req.info or {})
    screen.health_state = Screen.Health.OFFLINE
    screen.save()
    if groups and not repair:
        screen.manual_groups.set(groups)
    req.screen, req.claimed_at, req.token_encrypted = screen, timezone.now(), crypto.encrypt(raw)
    req.save(update_fields=["screen", "claimed_at", "token_encrypted"])
    log(action="screen.repaired" if repair else "screen.paired", actor=actor, target=screen, event=event,
        request=request, message=f"Screen {screen.name} paired (code {req.display_code})",
        scope={"screen": str(screen.pk)})
    webhooks.emit("screen.paired", {"screen": str(screen.pk), "name": screen.name, "repaired": repair},
                  event=event)
    return screen


def pairing_status(req: PairingRequest, secret: str) -> dict[str, Any]:
    """What the waiting player gets: ``pending``, ``expired``, or (once) ``paired`` with its device token."""
    if not secrets.compare_digest(req.secret_hash, hash_secret(secret or "")):
        raise PermissionError("wrong pairing secret")
    if req.claimed_at is None:
        if req.is_expired:
            return {"status": "expired"}
        return {"status": "pending", "code": req.display_code,
                "expires_in": int((req.expires_at - timezone.now()).total_seconds())}
    if not req.token_encrypted:
        return {"status": "delivered"}
    token = crypto.decrypt(req.token_encrypted)
    PairingRequest.objects.filter(pk=req.pk).update(token_encrypted="", delivered_at=timezone.now())
    screen = req.screen
    return {"status": "paired", "token": token, "screen": {"id": str(screen.pk), "name": screen.name},
            "event": {"slug": screen.event.slug, "name": screen.event.name}}


def purge_pairing_requests() -> int:
    cutoff = timezone.now() - dt.timedelta(days=1)
    return PairingRequest.objects.filter(expires_at__lt=cutoff).delete()[0]


# --------------------------------------------------------------------------- device authentication

def authenticate(raw: str | None) -> Screen | None:
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    return (Screen.objects.select_related("event", "venue", "zone", "room")
            .filter(token_hash=hash_secret(raw), revoked_at__isnull=True).first())


def _clean_reported(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, limit in REPORTED_KEYS.items():
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            out[key] = value[:limit] if limit else value[:200]
        elif isinstance(value, bool) or value is None:
            out[key] = value
        elif isinstance(value, int | float):
            out[key] = value
        elif key == "errors" and isinstance(value, list):
            out[key] = [str(e)[:300] for e in value[:10]]
    return out


def heartbeat(screen: Screen, data: dict[str, Any], *, ip: str | None = None) -> dict[str, Any]:
    """Store what the player reported; answer with the server time (for offset sync) and its settings."""
    reported = _clean_reported(data)
    now = timezone.now()
    previous = screen.health_state
    Screen.objects.filter(pk=screen.pk).update(last_seen_at=now, last_ip=ip, reported=reported,
                                               health_state=Screen.Health.ONLINE)
    screen.last_seen_at, screen.reported, screen.health_state = now, reported, Screen.Health.ONLINE
    if previous in (Screen.Health.OFFLINE, Screen.Health.STALE):
        _health_changed(screen, previous, Screen.Health.ONLINE)
    return {"server_time": now.timestamp(), "heartbeat_seconds": screen_settings(screen.event)["heartbeat_seconds"]}


def sweep_health(now=None) -> int:
    """Detect screens that went stale/offline (periodic task). Returns the number of state changes."""
    now = now or timezone.now()
    changed = 0
    for screen in Screen.objects.paired().select_related("event").filter(
            health_state__in=[Screen.Health.ONLINE, Screen.Health.STALE]):
        cfg = screen_settings(screen.event)
        state = screen.health(heartbeat_seconds=cfg["heartbeat_seconds"], offline_after=cfg["offline_after_seconds"],
                              now=now)
        if state != screen.health_state:
            previous = screen.health_state
            Screen.objects.filter(pk=screen.pk).update(health_state=state)
            screen.health_state = state
            _health_changed(screen, previous, state)
            changed += 1
    return changed


def _health_changed(screen: Screen, previous: str, state: str) -> None:
    payload = {"screen": str(screen.pk), "name": screen.name, "state": state, "previous": previous}
    if state == Screen.Health.OFFLINE:
        webhooks.emit("screen.offline", payload, event=screen.event)
        if screen_settings(screen.event).get("alert_offline", True):
            _notify_offline(screen)
    elif state == Screen.Health.ONLINE and previous == Screen.Health.OFFLINE:
        webhooks.emit("screen.online", payload, event=screen.event)
    else:
        from apps.core import realtime

        realtime.publish(screen.event, "screen.health", payload)


def _notify_offline(screen: Screen) -> None:
    from django.urls import reverse

    from apps.core.notify import notify
    from apps.events import rbac

    chain = rbac.scope_chain(screen)
    users = [m.user for m in screen.event.memberships.select_related("user").filter(user__is_active=True)
             if rbac.effective(m.user, screen.event, two_factor=True).access.allows("screens.manage", chain)]
    notify(users, _("Screen offline: %(name)s") % {"name": screen.name}, level="warning", event=screen.event,
           url=reverse("screens:detail", args=[screen.event.slug, screen.pk]),
           body=_("No heartbeat since %(time)s.") % {
               "time": timezone.localtime(screen.last_seen_at).strftime("%H:%M:%S") if screen.last_seen_at else "-"})


# --------------------------------------------------------------------------- screens and groups

def _clean_tags(tags) -> list[str]:
    if isinstance(tags, str):
        tags = tags.split(",")
    seen: list[str] = []
    for t in tags or []:
        t = str(t).strip().lower()[:40]
        if t and t not in seen:
            seen.append(t)
    return seen[:30]


def save_screen(screen: Screen, *, actor, request=None, before: dict[str, Any] | None = None,
                groups=None) -> Screen:
    creating = screen._state.adding
    screen.tags = _clean_tags(screen.tags)
    screen.full_clean(exclude=["event", "manual_groups"])
    screen.save()
    if groups is not None:
        screen.manual_groups.set(groups)
    changes = None
    if before:
        changes = {k: [v, getattr(screen, k)] for k, v in before.items() if v != getattr(screen, k)}
    log(action="screen.created" if creating else "screen.updated", actor=actor, target=screen, event=screen.event,
        request=request, changes=changes, scope={"screen": str(screen.pk)})
    channel.send(screen, "config.changed", {})
    return screen


def revoke(screen: Screen, *, actor, request=None) -> None:
    screen.revoked_at = timezone.now()
    screen.health_state = Screen.Health.REVOKED
    screen.save(update_fields=["revoked_at", "health_state", "updated_at"])
    log(action="screen.revoked", actor=actor, target=screen, event=screen.event, request=request,
        message=f"Device token of {screen.name} revoked", scope={"screen": str(screen.pk)})
    channel.send(screen, "revoked", {})
    webhooks.emit("screen.revoked", {"screen": str(screen.pk), "name": screen.name}, event=screen.event)


def delete_screen(screen: Screen, *, actor, request=None) -> None:
    channel.send(screen, "revoked", {})
    log(action="screen.deleted", actor=actor, target=screen, event=screen.event, request=request,
        message=f"Screen {screen.name} deleted")
    screen.delete()


def save_group(group: ScreenGroup, *, actor, request=None, m2m: dict[str, Any] | None = None) -> ScreenGroup:
    creating = group._state.adding
    group.match_tags = _clean_tags(group.match_tags)
    group.save()
    for field, values in (m2m or {}).items():
        getattr(group, field).set(values)
    log(action="screen_group.created" if creating else "screen_group.updated", actor=actor, target=group,
        event=group.event, request=request, scope={"screen_group": str(group.pk)})
    return group


def delete_group(group: ScreenGroup, *, actor, request=None) -> None:
    log(action="screen_group.deleted", actor=actor, target=group, event=group.event, request=request,
        message=f"Screen group {group.name} deleted")
    group.delete()
