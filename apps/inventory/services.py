# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inventory services (ADR-0042): items with asset tags, lend and return, reminders, labels, the map layer."""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import re
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core import modules, settings_store, webhooks
from apps.core.audit import log

from .models import Item, Loan, Note

MODULE = "inventory"
MAX_SIGNATURE = 300 * 1024


def inv_settings(event: Any) -> dict[str, Any]:
    return settings_store.get("inventory", event=event)


def _user(actor: Any) -> Any:
    return actor if getattr(actor, "pk", None) and getattr(actor, "is_authenticated", True) else None


def next_tag(event: Any) -> str:
    prefix = str(inv_settings(event).get("tag_prefix") or "EV-")
    n = 0
    for tag in Item.objects.filter(event=event, asset_tag__startswith=prefix).values_list("asset_tag", flat=True):
        m = re.fullmatch(re.escape(prefix) + r"(\d+)", tag)
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:04d}"


def save_item(item: Item, *, actor: Any, request: Any = None, copies: int = 1) -> list[Item]:
    """Create (``copies`` items with consecutive tags) or edit an item."""
    if not item.name.strip():
        raise ValidationError(_("Give the item a name."))
    created = item._state.adding
    if not created:
        item.save()
        log(action="inventory.item_edited", actor=actor, target=item, event=item.event, request=request,
            message=str(item))
        return [item]
    out = []
    for i in range(max(1, min(copies, 200))):
        obj = item if i == 0 else Item(**{f.attname: getattr(item, f.attname) for f in Item._meta.concrete_fields
                                          if f.name not in ("id", "asset_tag")})
        if i > 0 or not obj.asset_tag:
            obj.asset_tag = next_tag(item.event)
        try:
            with transaction.atomic():
                obj.save()
        except IntegrityError:
            raise ValidationError(_("The asset tag %(t)s is taken.") % {"t": obj.asset_tag}) from None
        out.append(obj)
    log(action="inventory.items_created", actor=actor, target=out[0], event=item.event, request=request,
        message=f"{len(out)} × {item.name} ({out[0].asset_tag}…{out[-1].asset_tag})")
    return out


def _signature_file(data_url: str) -> ContentFile | None:
    """A drawn signature from the page (``data:image/png;base64,…``)."""
    if not data_url:
        return None
    m = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=]+)", data_url.strip())
    if not m:
        raise ValidationError(_("The signature could not be read."))
    try:
        raw = base64.b64decode(m.group(1), validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError(_("The signature could not be read.")) from None
    if len(raw) > MAX_SIGNATURE or not raw.startswith(b"\x89PNG"):
        raise ValidationError(_("The signature could not be read."))
    return ContentFile(raw, name="signature.png")


def lend(item: Item, *, borrower: str, actor: Any, request: Any = None, borrower_user: Any = None,
         contact: str = "", due_at: dt.datetime | None = None, signature: str = "", photo: Any = None,
         notes: str = "") -> Loan:
    borrower = (borrower or (str(borrower_user) if borrower_user else "")).strip()
    if not borrower:
        raise ValidationError(_("Who gets it?"))
    if due_at is not None and due_at <= timezone.now():
        raise ValidationError(_("The due time must be in the future."))
    sig = _signature_file(signature)
    with transaction.atomic():
        locked = Item.objects.select_for_update().get(pk=item.pk)
        if locked.status != Item.Status.AVAILABLE:
            raise ValidationError(_("%(i)s is not available (%(s)s).") % {"i": locked,
                                                                          "s": locked.get_status_display()})
        loan = Loan(item=locked, borrower=borrower[:120], borrower_user=borrower_user, contact=contact[:120],
                    lent_at=timezone.now(), due_at=due_at, lent_by=_user(actor), notes=notes)
        if sig is not None:
            loan.signature.save(sig.name, sig, save=False)
        if photo is not None:
            loan.photo_out.save(getattr(photo, "name", "photo.jpg"), photo, save=False)
        loan.save()
        locked.status = Item.Status.LENT
        locked.save(update_fields=["status"])
    item.status = Item.Status.LENT
    log(action="inventory.lent", actor=actor, target=locked, event=item.event, request=request,
        message=f"{locked} → {borrower}", changes={"due_at": due_at.isoformat() if due_at else None,
                                                   "signature": sig is not None, "photo": photo is not None})
    transaction.on_commit(lambda: webhooks.emit("inventory.lent", payload_of(loan), event=item.event))
    return loan


def return_item(loan: Loan, *, actor: Any, request: Any = None, condition: str = Loan.Condition.OK,
                photo: Any = None, notes: str = "") -> Loan:
    if loan.returned_at is not None:
        raise ValidationError(_("Already returned."))
    if condition not in Loan.Condition.values:
        condition = Loan.Condition.OK
    item = loan.item
    with transaction.atomic():
        loan.returned_at, loan.returned_by, loan.condition = timezone.now(), _user(actor), condition
        if notes:
            loan.notes = (loan.notes + "\n" + notes).strip()
        if photo is not None:
            loan.photo_back.save(getattr(photo, "name", "photo.jpg"), photo, save=False)
        loan.save()
        item.status = Item.Status.AVAILABLE if condition == Loan.Condition.OK else Item.Status.MAINTENANCE
        item.save(update_fields=["status"])
        if condition != Loan.Condition.OK:
            Note.objects.create(item=item, kind=Note.Kind.DAMAGE, actor=_user(actor),
                                text=_("Returned %(c)s by %(b)s") % {"c": loan.get_condition_display().lower(),
                                                                     "b": loan.borrower} + (f": {notes}" if notes
                                                                                             else ""))
    log(action="inventory.returned", actor=actor, target=item, event=item.event, request=request,
        message=f"{item} ← {loan.borrower} ({condition})")
    transaction.on_commit(lambda: webhooks.emit("inventory.returned", payload_of(loan), event=item.event))
    return loan


def add_note(item: Item, text: str, *, kind: str, actor: Any, request: Any = None,
             status: str | None = None) -> Note:
    text = (text or "").strip()
    if not text and not status:
        raise ValidationError(_("Write a note."))
    if status:
        if status not in Item.Status.values:
            raise ValidationError(_("Unknown status."))
        if status == Item.Status.LENT or (item.status == Item.Status.LENT and status != item.status):
            raise ValidationError(_("Lend and return change that status."))
        item.status = status
        item.save(update_fields=["status"])
        text = (_("Status: %(s)s") % {"s": item.get_status_display()}) + (f". {text}" if text else "")
        kind = Note.Kind.STATUS
    n = Note.objects.create(item=item, kind=kind if kind in Note.Kind.values else Note.Kind.NOTE, text=text,
                            actor=_user(actor))
    log(action=f"inventory.{n.kind}", actor=actor, target=item, event=item.event, request=request, message=text[:200])
    return n


def payload_of(loan: Loan) -> dict[str, Any]:
    return {"item": loan.item.asset_tag, "name": loan.item.name, "event": loan.item.event.slug,
            "borrower": loan.borrower, "lent_at": loan.lent_at.isoformat(),
            "due_at": loan.due_at.isoformat() if loan.due_at else None,
            "returned_at": loan.returned_at.isoformat() if loan.returned_at else None,
            "condition": loan.condition}


def remind_overdue(now: dt.datetime | None = None) -> int:
    """Beat task: loans past their due time remind the borrower (with an account) and whoever lent it, once."""
    from apps.core.notify import notify

    now = now or timezone.now()
    n = 0
    for loan in (Loan.objects.filter(returned_at__isnull=True, due_at__lt=now, reminded_at__isnull=True)
                 .select_related("item__event", "borrower_user", "lent_by")):
        event = loan.item.event
        if not modules.is_enabled(MODULE, event):
            continue
        users = [u for u in (loan.borrower_user, loan.lent_by) if u is not None]
        notify(users, _("Please bring back %(i)s") % {"i": loan.item},
               body=_("It was due at %(t)s.") % {"t": timezone.localtime(loan.due_at).strftime("%a %H:%M")},
               url=f"/e/{event.slug}/inventory/t/{loan.item.asset_tag}/", level="warn", event=event)
        loan.reminded_at = now
        loan.save(update_fields=["reminded_at"])
        webhooks.emit("inventory.overdue", payload_of(loan), event=event)
        n += 1
    return n


def open_loans(event: Any) -> Any:
    return (Loan.objects.filter(item__event=event, returned_at__isnull=True)
            .select_related("item", "item__category", "borrower_user").order_by("due_at", "lent_at"))


# ------------------------------------------------------------------ map layer (ADR-0027)
def map_items(event: Any, venue: Any) -> list[dict[str, Any]]:
    from django.db.models import Q

    out = []
    for it in Item.objects.filter(event=event).exclude(status=Item.Status.RETIRED).filter(
            Q(floor__building__venue=venue) | Q(floor__isnull=True)).order_by("asset_tag")[:500]:
        placed = it.position_x is not None and it.floor_id is not None
        out.append({"id": str(it.pk), "label": f"{it.asset_tag} {it.name}", "placed": placed,
                    "floor": str(it.floor_id) if it.floor_id else None, "x": it.position_x, "y": it.position_y,
                    "facing": None, "state": it.status})
    return out


def map_place(event: Any, item_id: str, *, floor: Any, x: Any, y: Any, facing: Any, actor: Any,
              request: Any = None) -> None:
    from django.core.exceptions import PermissionDenied

    from apps.events import rbac

    it = Item.objects.filter(event=event, pk=item_id).first() if len(item_id) == 36 else None
    if it is None:
        raise ValidationError(_("Unknown item."))
    if not rbac.has_perm(actor, event, "inventory.manage", request=request):
        raise PermissionDenied(_("You may not move items."))
    if x is None:
        it.floor, it.position_x, it.position_y = None, None, None
    else:
        it.floor, it.position_x, it.position_y = floor, x, y
    it.save(update_fields=["floor", "position_x", "position_y"])
    log(action="inventory.placed", actor=actor, target=it, event=event, request=request, message=str(it))


def map_rescale(floor: Any, factor: float) -> None:
    for it in Item.objects.filter(floor=floor).exclude(position_x=None):
        it.position_x, it.position_y = it.position_x * factor, (it.position_y or 0) * factor
        it.save(update_fields=["position_x", "position_y"])
