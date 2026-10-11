# SPDX-License-Identifier: AGPL-3.0-or-later
"""Access services (ADR-0044): attendees and ticket types, the scanner rules, offline lists and scan batches,
presence per zone and the occupancy feed.

The rule (:func:`decide`) is the same on the server and, simplified, in the scanner page: unknown code →
unknown; cancelled or blocked → invalid; zone not granted → denied; into a zone without re-entry while already
inside → duplicate; else OK. The server's answer wins: a device that was offline learns afterwards that a ticket
was, say, already let in at another door.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core import modules, settings_store, webhooks
from apps.core.audit import log

from .models import AccessZone, Attendee, Presence, Scan, TicketType, new_code

MODULE = "access"
MAX_BATCH = 500


def access_settings(event: Any) -> dict[str, Any]:
    return settings_store.get("access", event=event)


def _user(actor: Any) -> Any:
    return actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True) else None


def code_key(code: str) -> str:
    """What the offline list stores instead of the code: the first 20 hex digits of its SHA-256."""
    return hashlib.sha256(code.strip().encode()).hexdigest()[:20]


# ------------------------------------------------------------------ editing
def save_attendee(a: Attendee, *, actor: Any, request: Any = None) -> Attendee:
    if not a.name.strip():
        raise ValidationError(_("Give a name."))
    created = a._state.adding
    a.code = (a.code or "").strip() or new_code()
    try:
        with transaction.atomic():
            a.save()
    except IntegrityError:
        raise ValidationError(_("This ticket code is taken.")) from None
    log(action="access.attendee_" + ("added" if created else "edited"), actor=actor, target=a, event=a.event,
        request=request, message=f"{a.name} ({a.ticket_type})")
    return a


def set_status(a: Attendee, status: str, *, actor: Any, request: Any = None) -> Attendee:
    if status not in Attendee.Status.values:
        raise ValidationError(_("Unknown status."))
    before = a.status
    a.status = status
    a.save(update_fields=["status"])
    log(action="access.attendee_status", actor=actor, target=a, event=a.event, request=request,
        changes={"status": [before, status]}, message=a.name)
    return a


IMPORT_FIELDS = ("name", "email", "company", "ticket_type", "code")


def import_csv(event: Any, raw: bytes, *, actor: Any, request: Any = None) -> dict[str, int]:
    """Columns ``name, email, company, ticket_type, code`` (header row; only ``name`` and ``ticket_type`` are
    needed). Unknown ticket types are created; an existing code updates that attendee."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError(_("The file is not UTF-8 text.")) from None
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not {"name", "ticket_type"} <= {f.strip().lower() for f in reader.fieldnames}:
        raise ValidationError(_("The first row must name the columns, at least name and ticket_type."))
    types = {t.name.lower(): t for t in TicketType.objects.filter(event=event)}
    stats = {"added": 0, "updated": 0, "skipped": 0, "types": 0}
    with transaction.atomic():
        for n, row in enumerate(reader):
            if n >= 20_000:
                break
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            name, tname = row.get("name", "")[:150], row.get("ticket_type", "")[:80]
            if not name or not tname:
                stats["skipped"] += 1
                continue
            t = types.get(tname.lower())
            if t is None:
                t = types[tname.lower()] = TicketType.objects.create(event=event, name=tname)
                stats["types"] += 1
            code = row.get("code", "")[:128]
            a = Attendee.objects.filter(event=event, code=code).first() if code else None
            if a is None:
                Attendee.objects.create(event=event, name=name, email=row.get("email", "")[:254],
                                        company=row.get("company", "")[:150], ticket_type=t,
                                        code=code or new_code(), source="csv")
                stats["added"] += 1
            else:
                a.name, a.ticket_type = name, t
                a.email, a.company = row.get("email", a.email)[:254], row.get("company", a.company)[:150]
                a.save()
                stats["updated"] += 1
    log(action="access.imported", actor=actor, event=event, request=request,
        message=f"{stats['added']} added, {stats['updated']} updated, {stats['skipped']} skipped")
    return stats


# ------------------------------------------------------------------ the rule
def granted(zone: AccessZone, ticket_type_id: Any) -> bool:
    return zone.open_to_all or zone.ticket_types.filter(pk=ticket_type_id).exists()


def decide(zone: AccessZone, attendee: Attendee | None, direction: str, inside: bool) -> tuple[str, str]:
    """``(result, message)`` for a scan; pure apart from the zone's ticket types."""
    if attendee is None:
        return Scan.Result.UNKNOWN, _("Unknown ticket")
    if not attendee.is_valid:
        return Scan.Result.INVALID, _("Ticket %(s)s") % {"s": attendee.get_status_display().lower()}
    if direction == Scan.Direction.IN:
        if not granted(zone, attendee.ticket_type_id):
            return Scan.Result.DENIED, _("%(t)s does not grant %(z)s") % {"t": attendee.ticket_type, "z": zone}
        if inside and not zone.reentry:
            return Scan.Result.DUPLICATE, _("Already inside")
    return Scan.Result.OK, (_("Welcome, %(n)s") if direction == Scan.Direction.IN else _("Goodbye, %(n)s")) % {
        "n": attendee.name}


def scan(zone: AccessZone, code: str, *, direction: str = "in", actor: Any = None, at: dt.datetime | None = None,
         client_id: str = "", device: str = "", offline: bool = False, source: str = "scanner") -> tuple[Scan, str]:
    """Apply one scan. Returns ``(scan, message)``; a replay of ``client_id`` returns the stored scan."""
    event = zone.event
    client_id = (client_id or "")[:64]
    if client_id:
        old = Scan.objects.filter(event=event, client_id=client_id).select_related("attendee").first()
        if old is not None:
            return old, _("Already received")
    direction = Scan.Direction.OUT if direction == "out" else Scan.Direction.IN
    now = timezone.now()
    when = min(at, now) if at is not None and at > now - dt.timedelta(days=2) else now
    code = (code or "").strip()[:128]
    try:
        with transaction.atomic():
            attendee = Attendee.objects.select_for_update().filter(event=event, code=code).first() if code else None
            presence = Presence.objects.filter(attendee=attendee, zone=zone).first() if attendee else None
            result, message = decide(zone, attendee, direction, bool(presence and presence.inside))
            s = Scan.objects.create(event=event, zone=zone, attendee=attendee, direction=direction, result=result,
                                    at=when, offline=offline, device=device[:80], user=_user(actor),
                                    client_id=client_id, source=source,
                                    code_hint="" if attendee else code[-4:])
            changed = False
            if result == Scan.Result.OK and attendee is not None:
                inside = direction == Scan.Direction.IN
                was_inside = bool(presence and presence.inside)
                if presence is None:
                    Presence.objects.create(attendee=attendee, zone=zone, inside=inside, since=when)
                else:
                    presence.inside, presence.since = inside, when
                    presence.save(update_fields=["inside", "since"])
                changed = inside != was_inside
                if inside and zone.checkin and attendee.checked_in_at is None:
                    attendee.checked_in_at = when
                    attendee.save(update_fields=["checked_in_at"])
                    transaction.on_commit(lambda: webhooks.emit("access.checked_in", payload_of(attendee, zone),
                                                                event=event))
                if changed:
                    _count(zone, 1 if inside else -1, s)
    except IntegrityError:  # the same client id at the same moment
        return Scan.objects.get(event=event, client_id=client_id), _("Already received")
    if s.result != Scan.Result.OK:
        transaction.on_commit(lambda: webhooks.emit("access.refused", {
            "zone": zone.name, "result": s.result, "attendee": attendee.name if attendee else None,
            "at": when.isoformat(), "device": s.device}, event=event))
    return s, message


def _count(zone: AccessZone, delta: int, s: Scan) -> None:
    """Scans in and out feed the zone's occupancy area (ADR-0040), when the occupancy module is on."""
    from django.apps import apps

    if not zone.area_id or not apps.is_installed("apps.crowd") or not modules.is_enabled("crowd", zone.event):
        return
    from apps.crowd import services as crowd
    from apps.crowd.models import Area, CountEvent

    area = Area.objects.filter(event=zone.event, pk=zone.area_id).first()
    if area is not None:
        crowd.count(area, delta, source=CountEvent.Source.SCANNER, device=(s.device or zone.name)[:80],
                    client_id=f"scan:{s.pk}", at=s.at)


def batch(event: Any, items: list[Any], *, actor: Any, can_scan: Any) -> list[dict[str, Any]]:
    """The scanner's queue: ``[{"id", "zone", "code", "dir", "at", "device", "offline"}]``, oldest first.
    ``can_scan(zone)`` checks the permission per zone."""
    zones: dict[str, AccessZone | None] = {}
    out = []
    for it in items[:MAX_BATCH]:
        if not isinstance(it, dict):
            continue
        zid = str(it.get("zone") or "")
        if zid not in zones:
            z = AccessZone.objects.filter(event=event, pk=zid).select_related("event").first() if len(zid) == 36 \
                else None
            zones[zid] = z if z is not None and can_scan(z) else None
        zone = zones[zid]
        if zone is None:
            out.append({"id": it.get("id"), "result": "refused", "message": _("Not allowed to scan here")})
            continue
        s, message = scan(zone, str(it.get("code") or ""), direction=str(it.get("dir") or "in"), actor=actor,
                          at=parse_datetime(str(it.get("at") or "")), client_id=str(it.get("id") or ""),
                          device=str(it.get("device") or ""), offline=bool(it.get("offline")))
        out.append({"id": it.get("id"), "result": s.result, "message": message,
                    "name": s.attendee.name if s.attendee else ""})
    return out


def offline_list(zone: AccessZone) -> dict[str, Any]:
    """What a scanner keeps for offline use: per ticket only a hash of its code, the name, the ticket type and
    whether it is valid; plus which ticket types the zone admits."""
    event = zone.event
    types = list(TicketType.objects.filter(event=event))
    allowed = [str(t.pk) for t in types] if zone.open_to_all else [str(pk) for pk in
                                                                    zone.ticket_types.values_list("pk", flat=True)]
    inside = set(Presence.objects.filter(zone=zone, inside=True).values_list("attendee_id", flat=True))
    rows = {}
    for a in Attendee.objects.filter(event=event).only("id", "name", "code", "status", "ticket_type_id"):
        rows[code_key(a.code)] = [a.name, str(a.ticket_type_id), 1 if a.is_valid else 0, 1 if a.pk in inside else 0]
    return {"zone": {"id": str(zone.pk), "name": zone.name, "reentry": zone.reentry, "allowed": allowed},
            "types": {str(t.pk): {"name": t.name, "colour": t.colour} for t in types},
            "tickets": rows, "generated": timezone.now().isoformat(), "count": len(rows)}


def payload_of(a: Attendee, zone: AccessZone | None = None) -> dict[str, Any]:
    return {"id": str(a.pk), "name": a.name, "ticket_type": a.ticket_type.name, "status": a.status,
            "event": a.event.slug, "zone": zone.name if zone else None,
            "checked_in_at": a.checked_in_at.isoformat() if a.checked_in_at else None,
            "source": a.source, "external_id": a.external_id}


def stats(event: Any) -> dict[str, Any]:
    from django.db.models import Count, Q

    total = Attendee.objects.filter(event=event, status=Attendee.Status.VALID).count()
    checked = Attendee.objects.filter(event=event, status=Attendee.Status.VALID, checked_in_at__isnull=False).count()
    zones = AccessZone.objects.filter(event=event).annotate(n=Count("presence", filter=Q(presence__inside=True)))
    return {"total": total, "checked_in": checked, "zones": list(zones),
            "refused": Scan.objects.filter(event=event).exclude(result=Scan.Result.OK).count()}
