# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inventory pages: the list (who has what), an item with its QR code, lend/return/notes, new and edited items,
categories and the printable label sheet. ``t/<asset tag>/`` is what the QR label opens."""
from __future__ import annotations

import datetime as dt
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import services
from .forms import CategoryForm, ItemForm, LendForm, NoteForm, ReturnForm
from .models import Category, Item

MODULE = "inventory"


def _fail(request: Any, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


def _tz(event: Any) -> Any:
    import zoneinfo

    try:
        return zoneinfo.ZoneInfo(event.timezone or "UTC")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return zoneinfo.ZoneInfo("UTC")


def _label_url(request: Any, event: Any, item: Item) -> str:
    return request.build_absolute_uri(reverse("inventory:tag", args=[event.slug, item.asset_tag]))


@event_view("inventory.view", module=MODULE)
def index(request, slug, *, event):
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status") or ""
    cat = request.GET.get("category") or ""
    items = Item.objects.filter(event=event).select_related("category", "room")
    if q:
        items = items.filter(Q(name__icontains=q) | Q(asset_tag__icontains=q) | Q(serial__icontains=q)
                             | Q(loans__borrower__icontains=q, loans__returned_at__isnull=True)).distinct()
    if status in Item.Status.values:
        items = items.filter(status=status)
    if cat:
        items = items.filter(category_id=cat) if len(cat) == 36 else items.none()
    items = list(items[:1000])
    loans = {ln.item_id: ln for ln in services.open_loans(event)}
    for it in items:
        it.loan = loans.get(it.pk)
    can_manage = rbac.has_any(request.user, event, "inventory.manage", request=request)
    cform = CategoryForm(request.POST or None, instance=Category(event=event), prefix="cat") if can_manage else None
    if request.method == "POST":
        if cform is None:
            raise PermissionDenied("inventory.manage")
        if cform.is_valid():
            cform.save()
            messages.success(request, _("Category added."))
            return redirect("inventory:index", slug)
    now = timezone.now()
    with timezone.override(_tz(event)):
        return render(request, "inventory/index.html", {
            "event": event, "items": items, "q": q, "status": status, "category": cat,
            "statuses": Item.Status.choices, "categories": Category.objects.filter(event=event),
            "loans": list(loans.values()), "overdue": sum(1 for ln in loans.values() if ln.due_at and ln.due_at < now),
            "now": now, "can_manage": can_manage, "cform": cform,
            "can_lend": rbac.has_any(request.user, event, "inventory.lend", request=request)})


@event_view("inventory.view", module=MODULE)
def tag(request, slug, tag, *, event):
    """The QR label's URL."""
    it = get_object_or_404(Item, event=event, asset_tag=tag)
    return redirect("inventory:item", slug, it.pk)


@event_view("inventory.view", module=MODULE)
def item(request, slug, pk, *, event):
    it = get_object_or_404(Item.objects.select_related("category", "room"), event=event, pk=pk)
    loan = it.loans.filter(returned_at__isnull=True).first()
    can_lend = rbac.has_any(request.user, event, "inventory.lend", request=request)
    can_manage = rbac.has_any(request.user, event, "inventory.manage", request=request)
    with timezone.override(_tz(event)):
        initial = {}
        if it.category and it.category.loan_hours:
            initial["due_at"] = timezone.localtime() + dt.timedelta(hours=it.category.loan_hours)
        url = _label_url(request, event, it)
        from apps.accounts.twofactor import qr_svg

        return render(request, "inventory/item.html", {
            "event": event, "item": it, "loan": loan, "can_lend": can_lend, "can_manage": can_manage,
            "lend": LendForm(event=event, initial=initial, prefix="lend") if can_lend and not loan else None,
            "back": ReturnForm(prefix="back") if can_lend and loan else None,
            "note": NoteForm(prefix="note") if can_manage else None,
            "history": it.loans.select_related("lent_by", "returned_by")[:50], "notes": it.notes.all()[:50],
            "qr": qr_svg(url), "url": url, "now": timezone.now(),
            "signature_required": bool(services.inv_settings(event).get("signature_required"))})


@require_POST
@event_view("inventory.lend", module=MODULE)
def lend(request, slug, pk, *, event):
    it = get_object_or_404(Item, event=event, pk=pk)
    with timezone.override(_tz(event)):
        form = LendForm(request.POST, request.FILES, event=event, prefix="lend")
        if not form.is_valid():
            for errs in form.errors.values():
                for e in errs:
                    messages.error(request, e)
            return redirect("inventory:item", slug, it.pk)
    d = form.cleaned_data
    if services.inv_settings(event).get("signature_required") and not d.get("signature"):
        messages.error(request, _("Please sign first."))
        return redirect("inventory:item", slug, it.pk)
    try:
        services.lend(it, borrower=d.get("borrower") or "", borrower_user=d.get("borrower_user"),
                      contact=d.get("contact") or "", due_at=d.get("due_at"), signature=d.get("signature") or "",
                      photo=d.get("photo"), actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
    else:
        messages.success(request, _("%(i)s is lent.") % {"i": it})
    return redirect("inventory:item", slug, it.pk)


@require_POST
@event_view("inventory.lend", module=MODULE)
def give_back(request, slug, pk, *, event):
    it = get_object_or_404(Item, event=event, pk=pk)
    loan = it.loans.filter(returned_at__isnull=True).first()
    if loan is None:  # a replay from the offline queue, or someone was faster
        messages.info(request, _("%(i)s is already back.") % {"i": it})
        return redirect("inventory:item", slug, it.pk)
    form = ReturnForm(request.POST, request.FILES, prefix="back")
    form.is_valid()
    d = form.cleaned_data
    try:
        services.return_item(loan, condition=d.get("condition") or "ok", notes=d.get("notes") or "",
                             photo=d.get("photo"), actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
    else:
        messages.success(request, _("%(i)s is back.") % {"i": it})
    return redirect("inventory:item", slug, it.pk)


@require_POST
@event_view("inventory.manage", module=MODULE)
def note(request, slug, pk, *, event):
    it = get_object_or_404(Item, event=event, pk=pk)
    form = NoteForm(request.POST, prefix="note")
    if form.is_valid():
        d = form.cleaned_data
        try:
            services.add_note(it, d["text"], kind=d["kind"], status=d.get("status") or None, actor=request.user,
                              request=request)
        except ValidationError as err:
            _fail(request, err)
    return redirect("inventory:item", slug, it.pk)


@event_view("inventory.manage", module=MODULE)
def item_edit(request, slug, pk=None, *, event):
    it = get_object_or_404(Item, event=event, pk=pk) if pk else Item(event=event)
    form = ItemForm(request.POST or None, request.FILES or None, instance=it, event=event)
    if request.method == "POST" and form.is_valid():
        try:
            made = services.save_item(form.save(commit=False), actor=request.user, request=request,
                                      copies=form.cleaned_data.get("copies") or 1)
        except ValidationError as err:
            _fail(request, err)
        else:
            if len(made) > 1:
                messages.success(request, _("%(n)s items added.") % {"n": len(made)})
                return redirect(reverse("inventory:labels", args=[slug]) + "?from=" + made[0].asset_tag
                                + "&to=" + made[-1].asset_tag)
            messages.success(request, _("Saved."))
            return redirect("inventory:item", slug, made[0].pk)
    return render(request, "inventory/item_form.html", {"event": event, "form": form,
                                                        "obj": None if it._state.adding else it})


@event_view("inventory.manage", module=MODULE)
def labels(request, slug, *, event):
    """A sheet of QR labels to print (all, one category, or a tag range)."""
    from apps.accounts.twofactor import qr_svg

    items = Item.objects.filter(event=event).exclude(status=Item.Status.RETIRED)
    cat = request.GET.get("category") or ""
    if cat:
        items = items.filter(category_id=cat) if len(cat) == 36 else items.none()
    lo, hi = request.GET.get("from") or "", request.GET.get("to") or ""
    if lo:
        items = items.filter(asset_tag__gte=lo)
    if hi:
        items = items.filter(asset_tag__lte=hi)
    labels = [{"item": it, "qr": qr_svg(_label_url(request, event, it))} for it in items[:300]]
    return render(request, "inventory/labels.html", {"event": event, "labels": labels})
