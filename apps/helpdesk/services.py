# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpdesk services (ADR-0043): lost & found with matching suggestions, requests with notes and replies, FAQ."""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import settings_store, webhooks
from apps.core.audit import log

from .models import FaqEntry, LostFound, Ticket, TicketNote

MODULE = "helpdesk"
WORD = re.compile(r"[a-z0-9äöüß]{3,}")
STOP = {"the", "and", "with", "for", "black", "white", "small", "big", "large", "lost", "found", "near", "one"}


def hd_settings(event: Any) -> dict[str, Any]:
    return settings_store.get("helpdesk", event=event)


def _tz(event: Any) -> Any:
    import zoneinfo

    try:
        return zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return zoneinfo.ZoneInfo("UTC")


def _user(actor: Any) -> Any:
    return actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True) else None


def _next_ref(model: Any, event: Any, prefix: str) -> str:
    n = 0
    for ref in model.objects.filter(event=event, reference__startswith=prefix).values_list("reference", flat=True):
        m = re.fullmatch(re.escape(prefix) + r"(\d+)", ref)
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:04d}"


def _save_with_ref(obj: Any, prefix: str) -> None:
    for _attempt in range(5):
        if not obj.reference:
            obj.reference = _next_ref(type(obj), obj.event, prefix)
        try:
            with transaction.atomic():
                obj.save()
            return
        except IntegrityError:
            obj.reference = ""
    raise ValidationError(_("Please try again."))


def staff_users(event: Any, perm: str = "helpdesk.manage") -> list[Any]:
    from apps.events import rbac
    from apps.events.models import Membership

    return [m.user for m in Membership.objects.filter(event=event, user__is_active=True).select_related("user")[:500]
            if rbac.has_any(m.user, event, perm)]


# ------------------------------------------------------------------ lost & found
def save_item(obj: LostFound, *, actor: Any, request: Any = None) -> LostFound:
    if not obj.what.strip():
        raise ValidationError(_("Say what it is."))
    created = obj._state.adding
    if created:
        obj.created_by = obj.created_by or _user(actor)
        _save_with_ref(obj, "L-" if obj.kind == LostFound.Kind.LOST else "F-")
    else:
        obj.save()
    log(action=f"helpdesk.{obj.kind}_{'reported' if created else 'edited'}", actor=actor, target=obj,
        event=obj.event, request=request, message=str(obj))
    if created:
        transaction.on_commit(lambda: webhooks.emit(f"helpdesk.{obj.kind}", lf_payload(obj), event=obj.event))
        if obj.source == "public":
            from apps.core.notify import notify

            notify(staff_users(obj.event), _("Lost report %(r)s: %(w)s") % {"r": obj.reference, "w": obj.what},
                   url=f"/e/{obj.event.slug}/helpdesk/lost-found/{obj.pk}/", event=obj.event)
    return obj


def lf_payload(obj: LostFound) -> dict[str, Any]:
    return {"reference": obj.reference, "kind": obj.kind, "what": obj.what, "category": obj.category,
            "colour": obj.colour, "status": obj.status, "event": obj.event.slug,
            "created_at": obj.created_at.isoformat() if obj.created_at else None}


def _words(obj: LostFound) -> set[str]:
    return {w for w in WORD.findall(f"{obj.what} {obj.description} {obj.colour}".lower()) if w not in STOP}


def score(a: LostFound, b: LostFound) -> int:
    s = 3 if a.category == b.category and a.category != "other" else 0
    if a.colour and b.colour and set(WORD.findall(a.colour.lower())) & set(WORD.findall(b.colour.lower())):
        s += 2
    s += min(4, len(_words(a) & _words(b)))
    lost, found = (a, b) if a.kind == LostFound.Kind.LOST else (b, a)
    if lost.when and found.when and found.when < lost.when - dt.timedelta(hours=6):
        s -= 3  # found long before it was lost
    if a.room_id and a.room_id == b.room_id:
        s += 1
    return s


def suggestions(obj: LostFound, limit: int = 5) -> list[tuple[int, LostFound]]:
    """Open items of the other kind that look alike, best first."""
    if obj.status != LostFound.Status.OPEN:
        return []
    other = LostFound.Kind.FOUND if obj.kind == LostFound.Kind.LOST else LostFound.Kind.LOST
    scored = [(score(obj, o), o) for o in LostFound.objects.filter(event=obj.event, kind=other,
                                                                   status=LostFound.Status.OPEN)[:1000]]
    return sorted([t for t in scored if t[0] >= 3], key=lambda t: -t[0])[:limit]


def match(a: LostFound, b: LostFound, *, actor: Any, request: Any = None) -> None:
    if a.kind == b.kind or a.event_id != b.event_id:
        raise ValidationError(_("Match a lost report with a found item."))
    if a.status != LostFound.Status.OPEN or b.status != LostFound.Status.OPEN:
        raise ValidationError(_("Both must still be open."))
    with transaction.atomic():
        for x, y in ((a, b), (b, a)):
            x.status, x.match = LostFound.Status.MATCHED, y
            x.save(update_fields=["status", "match"])
    lost = a if a.kind == LostFound.Kind.LOST else b
    log(action="helpdesk.matched", actor=actor, target=lost, event=a.event, request=request,
        message=f"{a.reference} ↔ {b.reference}")
    transaction.on_commit(lambda: webhooks.emit("helpdesk.matched", {"lost": lf_payload(lost),
                                                                     "found": lf_payload(lost.match)},
                                                event=a.event))


def unmatch(obj: LostFound, *, actor: Any, request: Any = None) -> None:
    other = obj.match
    with transaction.atomic():
        for x in (obj, other):
            if x is not None and x.status == LostFound.Status.MATCHED:
                x.status, x.match = LostFound.Status.OPEN, None
                x.save(update_fields=["status", "match"])
    log(action="helpdesk.unmatched", actor=actor, target=obj, event=obj.event, request=request, message=str(obj))


def hand_over(obj: LostFound, *, to: str, actor: Any, request: Any = None) -> None:
    """The found item goes back to its owner (and the matched lost report is done too)."""
    found = obj if obj.kind == LostFound.Kind.FOUND else obj.match
    if found is None:
        raise ValidationError(_("Match it with a found item first."))
    if found.status in (LostFound.Status.RETURNED, LostFound.Status.CLOSED):
        raise ValidationError(_("Already handed over or closed."))
    to = (to or (found.match.name if found.match else "")).strip()
    if not to:
        raise ValidationError(_("To whom?"))
    now = timezone.now()
    with transaction.atomic():
        for x in (found, found.match):
            if x is not None:
                x.status, x.handed_to, x.handed_at, x.handed_by = LostFound.Status.RETURNED, to[:120], now, _user(actor)
                x.save(update_fields=["status", "handed_to", "handed_at", "handed_by"])
    log(action="helpdesk.handed_over", actor=actor, target=found, event=found.event, request=request,
        message=f"{found} → {to}")
    transaction.on_commit(lambda: webhooks.emit("helpdesk.returned", lf_payload(found), event=found.event))


def close(obj: LostFound, *, actor: Any, request: Any = None, reason: str = "") -> None:
    obj.status = LostFound.Status.CLOSED
    obj.save(update_fields=["status"])
    log(action="helpdesk.closed", actor=actor, target=obj, event=obj.event, request=request,
        message=f"{obj}: {reason}"[:200])


def public_found(event: Any, limit: int = 100) -> Any:
    return LostFound.objects.filter(event=event, kind=LostFound.Kind.FOUND, public=True,
                                    status__in=(LostFound.Status.OPEN, LostFound.Status.MATCHED))[:limit]


# ------------------------------------------------------------------ requests
def submit(ticket: Ticket, *, actor: Any, request: Any = None) -> Ticket:
    if not ticket.subject.strip() or not ticket.body.strip():
        raise ValidationError(_("Write a subject and a message."))
    ticket.created_by = ticket.created_by or _user(actor)
    _save_with_ref(ticket, "R-")
    log(action="helpdesk.request", actor=actor, target=ticket, event=ticket.event, request=request,
        message=str(ticket))
    from apps.core.notify import notify

    notify(staff_users(ticket.event), _("Request %(r)s: %(s)s") % {"r": ticket.reference, "s": ticket.subject},
           body=ticket.body[:200], url=f"/e/{ticket.event.slug}/helpdesk/requests/{ticket.pk}/", event=ticket.event,
           level="warn" if ticket.category == "accessibility" else "info")
    transaction.on_commit(lambda: webhooks.emit("helpdesk.request", ticket_payload(ticket), event=ticket.event))
    return ticket


def ticket_payload(t: Ticket) -> dict[str, Any]:
    return {"reference": t.reference, "subject": t.subject, "category": t.category, "status": t.status,
            "source": t.source, "event": t.event.slug, "created_at": t.created_at.isoformat() if t.created_at else None}


def update(ticket: Ticket, *, actor: Any, request: Any = None, status: str | None = None, assignee: Any = ...,
           note: str = "", public: bool = False) -> Ticket:
    changes: dict[str, Any] = {}
    if status and status != ticket.status:
        if status not in Ticket.Status.values:
            raise ValidationError(_("Unknown status."))
        changes["status"] = [ticket.status, status]
        ticket.status = status
    if assignee is not ... and assignee != ticket.assignee:
        changes["assignee"] = str(assignee) if assignee else None
        ticket.assignee = assignee
        if assignee is not None and ticket.status == Ticket.Status.NEW:
            ticket.status = Ticket.Status.OPEN
    note = (note or "").strip()
    if not changes and not note:
        return ticket
    with transaction.atomic():
        ticket.save()
        if note:
            TicketNote.objects.create(ticket=ticket, text=note, public=public, actor=_user(actor))
            changes["note"] = "public reply" if public else "note"
    log(action="helpdesk.request_updated", actor=actor, target=ticket, event=ticket.event, request=request,
        changes=changes, message=str(ticket))
    if assignee is not ... and assignee is not None and assignee != _user(actor):
        from apps.core.notify import notify

        notify([assignee], _("Assigned to you: %(t)s") % {"t": ticket}, event=ticket.event,
               url=f"/e/{ticket.event.slug}/helpdesk/requests/{ticket.pk}/")
    return ticket


def open_tickets(event: Any) -> Any:
    return Ticket.objects.filter(event=event).exclude(status=Ticket.Status.DONE).select_related("assignee")


# ------------------------------------------------------------------ FAQ
def save_faq(entry: FaqEntry, *, actor: Any, request: Any = None) -> FaqEntry:
    created = entry._state.adding
    entry.save()
    log(action="helpdesk.faq_" + ("added" if created else "edited"), actor=actor, target=entry, event=entry.event,
        request=request, message=entry.question[:200])
    return entry


def delete_faq(entry: FaqEntry, *, actor: Any, request: Any = None) -> None:
    log(action="helpdesk.faq_deleted", actor=actor, target=entry, event=entry.event, request=request,
        message=entry.question[:200])
    entry.delete()
