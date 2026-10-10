# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpdesk pages: the queue (requests, lost & found), a request with notes and replies, lost & found with
matching suggestions and hand-over, the FAQ editor; and the public help page (FAQ, found items, the request and
lost-report forms, a status page per report)."""
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import modules
from apps.core.audit import client_ip
from apps.events.models import Event
from apps.portal.shortcuts import event_view

from . import services
from .forms import FaqForm, LostFoundForm, PublicLostForm, PublicTicketForm, TicketForm, UpdateForm
from .models import FaqEntry, LostFound, Ticket

MODULE = "helpdesk"


def _fail(request: Any, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


# ------------------------------------------------------------------ queue
@event_view("helpdesk.view", module=MODULE)
def index(request, slug, *, event):
    status = request.GET.get("status") or "open"
    tickets = Ticket.objects.filter(event=event).select_related("assignee")
    if status == "open":
        tickets = tickets.exclude(status=Ticket.Status.DONE)
    elif status == "mine":
        tickets = tickets.filter(assignee=request.user).exclude(status=Ticket.Status.DONE)
    elif status in Ticket.Status.values:
        tickets = tickets.filter(status=status)
    lf = LostFound.objects.filter(event=event)
    with timezone.override(services._tz(event)):
        return render(request, "helpdesk/index.html", {
            "event": event, "tickets": tickets[:300], "status": status, "statuses": Ticket.Status.choices,
            "lost_open": lf.filter(kind="lost", status="open").count(),
            "found_open": lf.filter(kind="found", status="open").count(),
            "matched": lf.filter(kind="found", status="matched").count(),
            "recent": lf.select_related("room")[:8],
            "public_url": request.build_absolute_uri(reverse("helpdesk_public:help", args=[slug]))})


@event_view("helpdesk.manage", module=MODULE)
def ticket_new(request, slug, *, event):
    form = TicketForm(request.POST or None, instance=Ticket(event=event))
    if request.method == "POST" and form.is_valid():
        try:
            t = services.submit(form.save(commit=False), actor=request.user, request=request)
        except ValidationError as err:
            _fail(request, err)
        else:
            return redirect("helpdesk:ticket", slug, t.pk)
    return render(request, "helpdesk/form.html", {"event": event, "form": form, "title": _("New request"),
                                                  "back": reverse("helpdesk:index", args=[slug])})


@event_view("helpdesk.view", module=MODULE)
def ticket(request, slug, pk, *, event):
    from apps.events import rbac

    t = get_object_or_404(Ticket.objects.select_related("assignee"), event=event, pk=pk)
    can_manage = rbac.has_any(request.user, event, "helpdesk.manage", request=request)
    form = UpdateForm(request.POST or None, event=event, initial={"status": t.status, "assignee": t.assignee},
                      prefix="u") if can_manage else None
    if request.method == "POST":
        if form is None:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("helpdesk.manage")
        if form.is_valid():
            d = form.cleaned_data
            try:
                services.update(t, status=d["status"], assignee=d["assignee"], note=d["note"], public=d["public"],
                                actor=request.user, request=request)
            except ValidationError as err:
                _fail(request, err)
            return redirect("helpdesk:ticket", slug, t.pk)
    with timezone.override(services._tz(event)):
        return render(request, "helpdesk/ticket.html", {
            "event": event, "t": t, "notes": t.notes.select_related("actor"), "form": form,
            "status_url": request.build_absolute_uri(reverse("helpdesk_public:status", args=[slug, t.token]))})


# ------------------------------------------------------------------ lost & found
@event_view("helpdesk.view", module=MODULE)
def lost_found(request, slug, *, event):
    kind = request.GET.get("kind") or ""
    status = request.GET.get("status") or "open"
    q = (request.GET.get("q") or "").strip()
    items = LostFound.objects.filter(event=event).select_related("room", "match")
    if kind in LostFound.Kind.values:
        items = items.filter(kind=kind)
    if status in LostFound.Status.values:
        items = items.filter(status=status)
    if q:
        items = items.filter(Q(what__icontains=q) | Q(description__icontains=q) | Q(colour__icontains=q)
                             | Q(reference__iexact=q) | Q(name__icontains=q))
    with timezone.override(services._tz(event)):
        return render(request, "helpdesk/lost_found.html", {
            "event": event, "items": items[:500], "kind": kind, "status": status, "q": q,
            "statuses": LostFound.Status.choices})


@event_view("helpdesk.manage", module=MODULE)
def lf_edit(request, slug, pk=None, *, event):
    if pk:
        obj = get_object_or_404(LostFound, event=event, pk=pk)
    else:
        obj = LostFound(event=event, kind="lost" if request.GET.get("kind") == "lost" else "found",
                        when=timezone.now())
    with timezone.override(services._tz(event)):
        form = LostFoundForm(request.POST or None, request.FILES or None, instance=obj, event=event)
        if request.method == "POST" and form.is_valid():
            try:
                obj = services.save_item(form.save(commit=False), actor=request.user, request=request)
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Saved as %(r)s.") % {"r": obj.reference})
                return redirect("helpdesk:lf", slug, obj.pk)
        title = (_("Edit %(r)s") % {"r": obj.reference}) if pk else (
            _("Report a lost item") if obj.kind == "lost" else _("Log a found item"))
        return render(request, "helpdesk/form.html", {"event": event, "form": form, "title": title, "files": True,
                                                      "back": reverse("helpdesk:lost_found", args=[slug])})


@event_view("helpdesk.view", module=MODULE)
def lf(request, slug, pk, *, event):
    from apps.events import rbac

    obj = get_object_or_404(LostFound.objects.select_related("room", "match", "handed_by"), event=event, pk=pk)
    with timezone.override(services._tz(event)):
        return render(request, "helpdesk/lf.html", {
            "event": event, "obj": obj, "suggestions": services.suggestions(obj),
            "can_manage": rbac.has_any(request.user, event, "helpdesk.manage", request=request),
            "status_url": request.build_absolute_uri(reverse("helpdesk_public:status", args=[slug, obj.token]))})


@require_POST
@event_view("helpdesk.manage", module=MODULE)
def lf_action(request, slug, pk, *, event):
    obj = get_object_or_404(LostFound.objects.select_related("match"), event=event, pk=pk)
    action = request.POST.get("action", "")
    try:
        if action == "match":
            other = get_object_or_404(LostFound, event=event, pk=request.POST.get("other"))
            services.match(obj, other, actor=request.user, request=request)
            messages.success(request, _("Matched with %(r)s.") % {"r": other.reference})
        elif action == "unmatch":
            services.unmatch(obj, actor=request.user, request=request)
        elif action == "hand_over":
            services.hand_over(obj, to=request.POST.get("to", ""), actor=request.user, request=request)
            messages.success(request, _("Handed over."))
        elif action == "close":
            services.close(obj, actor=request.user, request=request, reason=request.POST.get("reason", ""))
    except ValidationError as err:
        _fail(request, err)
    return redirect("helpdesk:lf", slug, obj.pk)


# ------------------------------------------------------------------ FAQ
@event_view("helpdesk.faq", module=MODULE)
def faq(request, slug, pk=None, *, event):
    entry = get_object_or_404(FaqEntry, event=event, pk=pk) if pk else FaqEntry(event=event)
    form = FaqForm(request.POST or None, instance=entry)
    if request.method == "POST":
        if request.POST.get("delete") and pk:
            services.delete_faq(entry, actor=request.user, request=request)
            messages.success(request, _("Deleted."))
            return redirect("helpdesk:faq", slug)
        if form.is_valid():
            services.save_faq(form.save(commit=False), actor=request.user, request=request)
            messages.success(request, _("Saved."))
            return redirect("helpdesk:faq", slug)
    return render(request, "helpdesk/faq.html", {"event": event, "form": form, "obj": entry if pk else None,
                                                 "entries": FaqEntry.objects.filter(event=event)})


# ------------------------------------------------------------------ public (no login)
def _public_event(slug: str) -> Event:
    event = get_object_or_404(Event, slug=slug)
    if not modules.is_enabled(MODULE, event) or not services.hd_settings(event).get("public_page", True):
        raise Http404
    return event


def _limited(request: Any) -> bool:
    """Per-IP limit for the public forms (the middleware's buckets match fixed path prefixes only)."""
    key = f"rl:helpdesk:{client_ip(request)}"
    try:
        cache.add(key, 0, 60)
        return cache.incr(key) > settings.EVAC_RATE_LIMITS.get("public_form", 10)
    except Exception:  # noqa: BLE001 - cache unavailable: fail open
        return False


def public(request, slug):
    event = _public_event(slug)
    cfg = services.hd_settings(event)
    entries = FaqEntry.objects.filter(event=event, public=True)
    topics: dict[str, list[FaqEntry]] = {}
    for e in entries:
        topics.setdefault(e.topic, []).append(e)
    with timezone.override(services._tz(event)):
        resp = render(request, "helpdesk/public.html", {
            "event": event, "topics": list(topics.items()),
            "found": services.public_found(event) if cfg.get("public_found", True) else None,
            "requests": cfg.get("public_requests", True), "lost": cfg.get("public_lost", True)})
    resp["Cache-Control"] = "public, max-age=30"
    return resp


def public_form(request, slug, what):
    event = _public_event(slug)
    cfg = services.hd_settings(event)
    if what == "request" and cfg.get("public_requests", True):
        form: Any = PublicTicketForm(request.POST or None, instance=Ticket(event=event, source="public"))
        title = _("Ask the helpdesk")
    elif what == "lost" and cfg.get("public_lost", True):
        form = PublicLostForm(request.POST or None, instance=LostFound(event=event, kind="lost", source="public"))
        title = _("Report a lost item")
    else:
        raise Http404
    if request.method == "POST":
        if _limited(request):
            return HttpResponse(_("Too many requests, please try again in a minute."), status=429,
                                content_type="text/plain")
        if form.is_valid():
            obj = form.save(commit=False)
            if form.cleaned_data.get("website"):  # honeypot: pretend it worked
                return redirect("helpdesk_public:help", slug)
            try:
                obj = (services.submit if what == "request" else services.save_item)(obj, actor=None,
                                                                                     request=request)
            except ValidationError as err:
                form.add_error(None, err)
            else:
                return redirect("helpdesk_public:status", slug, obj.token)
    return render(request, "helpdesk/public_form.html", {"event": event, "form": form, "title": title})


def public_status(request, slug, token):
    """What a visitor sees with their link: the state of their request or lost report and public replies."""
    event = _public_event(slug)
    t = Ticket.objects.filter(event=event, token=token).first()
    obj = None if t else get_object_or_404(LostFound, event=event, token=token)
    with timezone.override(services._tz(event)):
        resp = render(request, "helpdesk/public_status.html", {
            "event": event, "t": t, "obj": obj, "replies": t.notes.filter(public=True) if t else [],
            "url": request.build_absolute_uri()})
    resp["Cache-Control"] = "private, no-store"
    resp["Referrer-Policy"] = "no-referrer"
    return resp
