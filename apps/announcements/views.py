# SPDX-License-Identifier: AGPL-3.0-or-later
"""Announcement pages: overview, compose (with templates), detail with delivery report and approval, levels,
templates, and the public feed (HTML, RSS, JSON)."""
from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.feedgenerator import Rss201rev2Feed
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.core import modules
from apps.events import rbac
from apps.events.models import Event
from apps.playlists.services import _tz
from apps.portal.shortcuts import event_view

from . import forms, services
from .models import Announcement, Level, Template

ACTIVE = [Announcement.Status.SCHEDULED, Announcement.Status.LIVE]


def ann_view(perm: str):
    def deco(fn):
        @event_view(perm, module="announcements")
        @wraps(fn)
        def wrapper(request, slug, *args, event, **kwargs):
            services.ensure_defaults(event)
            with timezone.override(_tz(event)):
                return fn(request, slug, *args, event=event, **kwargs)
        return wrapper
    return deco


def _any(request, event, perm) -> bool:
    return rbac.has_any(request.user, event, perm, request=request)


def _can_compose(request, event) -> bool:
    return any(_any(request, event, p) for p in ("announcements.draft", "announcements.publish",
                                                 "announcements.emergency"))


def _fail(request, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


def _get(event, pk) -> Announcement:
    return get_object_or_404(Announcement.objects.filter(event=event).select_related("level", "created_by",
                                                                                     "decided_by"), pk=pk)


@ann_view("announcements.view")
def index(request, slug, *, event):
    qs = Announcement.objects.filter(event=event).select_related("level", "created_by")
    mine = Q(created_by=request.user)
    return render(request, "announcements/index.html", {
        "event": event,
        "active": qs.filter(status__in=ACTIVE).order_by("starts_at"),
        "pending": qs.filter(status=Announcement.Status.PENDING).order_by("submitted_at"),
        "drafts": qs.filter(mine, status__in=[Announcement.Status.DRAFT, Announcement.Status.REJECTED]),
        "history": qs.filter(status__in=[Announcement.Status.ENDED, Announcement.Status.CANCELLED,
                                         Announcement.Status.REJECTED]).exclude(mine & Q(
                                             status=Announcement.Status.REJECTED)).order_by("-updated_at")[:30],
        "templates": Template.objects.filter(event=event).select_related("level"),
        "can_compose": _can_compose(request, event),
        "can_approve": _any(request, event, "announcements.approve"),
        "can_manage": _any(request, event, "announcements.manage"),
        "feed_on": services.ann_settings(event).get("public_feed"),
    })


@ann_view("announcements.view")
def compose(request, slug, pk=None, *, event):
    if not _can_compose(request, event):
        raise PermissionDenied
    ann = _get(event, pk) if pk else Announcement(event=event)
    if pk and ann.status not in (Announcement.Status.DRAFT, Announcement.Status.REJECTED):
        messages.info(request, _("Only drafts can be edited."))
        return redirect("announcements:detail", slug, ann.pk)
    initial = {}
    tpl_pk = request.GET.get("template")
    if not pk and tpl_pk:
        tpl = Template.objects.filter(event=event, pk=tpl_pk).select_related("level").first() if _uuid(tpl_pk) \
            else None
        if tpl:
            initial = {"template": tpl.pk, "title": tpl.title, "body": tpl.body, "short": tpl.short}
            if tpl.level_id:
                initial["level"] = tpl.level_id
                initial["channels"] = tpl.level.default_channels
    if not pk and request.GET.get("level"):
        lv = Level.objects.filter(event=event, key=request.GET["level"]).first()
        if lv:
            initial.update(level=lv.pk, channels=lv.default_channels)
    if not pk and "channels" not in initial:
        first = Level.objects.filter(event=event, emergency=False).order_by("rank").first()
        if first and "level" not in initial:
            initial.update(level=first.pk, channels=first.default_channels)
    allow_emergency = _any(request, event, "announcements.emergency")
    form = forms.AnnouncementForm(request.POST or None, instance=ann, initial=initial, event=event,
                                  allow_emergency=allow_emergency)
    if request.method == "POST" and form.is_valid():
        built, m2m = form.build()
        try:
            services.save_draft(built, actor=request.user, request=request, m2m=m2m)
            if request.POST.get("action") == "send":
                services.submit(built, actor=request.user, request=request)
                if built.status == Announcement.Status.PENDING:
                    messages.success(request, _("Sent for approval."))
                elif built.status == Announcement.Status.LIVE:
                    messages.success(request, _("Published."))
                else:
                    messages.success(request, _("Scheduled."))
            else:
                messages.success(request, _("Draft saved."))
            return redirect("announcements:detail", slug, built.pk)
        except ValidationError as err:
            _fail(request, err)
        except PermissionDenied as err:
            messages.error(request, str(err) or _("You may not send this announcement."))
    return render(request, "announcements/compose.html", {
        "event": event, "form": form, "ann": ann, "template": form.template_obj,
        "levels": Level.objects.filter(event=event),
    })


def _uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


@ann_view("announcements.view")
def detail(request, slug, pk, *, event):
    ann = _get(event, pk)
    deliveries = list(ann.deliveries.all().order_by("-occurrence", "channel"))
    names = services.available_channels(event)
    for d in deliveries:
        d.channel_name = names.get(d.channel, d.channel)
    is_author = ann.created_by_id == request.user.pk
    perm = "announcements.emergency" if ann.level.emergency else "announcements.publish"
    return render(request, "announcements/detail.html", {
        "event": event, "ann": ann, "deliveries": deliveries,
        "channel_names": [names.get(c, c) for c in ann.channels],
        "audiences": services.audience_labels(ann), "anchor_text": services.anchor_text(ann),
        "can_edit": ann.status in (Announcement.Status.DRAFT, Announcement.Status.REJECTED) and (
            is_author or _any(request, event, "announcements.publish")),
        "can_approve": ann.status == Announcement.Status.PENDING and not is_author
        and services.may_target(request.user, ann, "announcements.approve", request),
        "can_cancel": ann.status in (*ACTIVE, Announcement.Status.PENDING) and (
            is_author or services.may_target(request.user, ann, perm, request)),
        "decision_form": forms.DecisionForm(),
        "speech_text": services.speech_text(ann) if ann.level.speak else "",
        "can_render": _any(request, event, "announcements.publish") or _any(request, event, "announcements.manage"),
        "windows": services.screen_windows(ann, timezone.now(), timezone.now() + services.dt.timedelta(days=1))[:10],
    })


def _action(fn, done: str):
    @require_POST
    @ann_view("announcements.view")
    def view(request, slug, pk, *, event):
        ann = _get(event, pk)
        kwargs = {}
        if fn in (services.approve, services.reject):
            kwargs["note"] = request.POST.get("note", "")[:300]
        try:
            fn(ann, actor=request.user, request=request, **kwargs)
            messages.success(request, str(done))
        except ValidationError as err:
            _fail(request, err)
        except PermissionDenied as err:
            messages.error(request, str(err) or _("Not allowed."))
        nxt = request.POST.get("next", "")
        if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
            return redirect(nxt)  # e.g. back to the staff page
        return redirect("announcements:detail", slug, ann.pk)
    return view


submit = _action(services.submit, gettext_lazy("Sent."))
approve = _action(services.approve, gettext_lazy("Approved."))
reject = _action(services.reject, gettext_lazy("Rejected."))
cancel = _action(services.cancel, gettext_lazy("Cancelled."))


@require_POST
@ann_view("announcements.view")
def delete(request, slug, pk, *, event):
    ann = _get(event, pk)
    try:
        services.delete_draft(ann, actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
        return redirect("announcements:detail", slug, ann.pk)
    messages.success(request, _("Draft deleted."))
    return redirect("announcements:index", slug)


@ann_view("announcements.view")
def speech(request, slug, pk, *, event):
    """The spoken file, for the preview on the announcement page."""
    from django.http import FileResponse

    from . import tts

    ann = _get(event, pk)
    if ann.speech_status != Announcement.Speech.READY or not tts.path_of(ann.speech_file).is_file():
        raise Http404
    return FileResponse(tts.path_of(ann.speech_file).open("rb"),
                        content_type="audio/mp4" if ann.speech_file.endswith(".m4a") else "audio/wav")


@require_POST
@ann_view("announcements.view")
def speech_render(request, slug, pk, *, event):
    ann = _get(event, pk)
    if not (_any(request, event, "announcements.publish") or _any(request, event, "announcements.manage")):
        raise PermissionDenied
    services.queue_speech(ann)
    messages.info(request, _("The spoken version is being prepared."))
    return redirect("announcements:detail", slug, ann.pk)


# ------------------------------------------------------------------ levels and templates
@ann_view("announcements.view")
def levels(request, slug, *, event):
    can_manage = _any(request, event, "announcements.manage")
    return render(request, "announcements/levels.html", {
        "event": event, "levels": Level.objects.filter(event=event), "can_manage": can_manage,
        "channel_names": services.available_channels(event)})


@ann_view("announcements.manage")
def level(request, slug, pk, *, event):
    lv = get_object_or_404(Level, event=event, pk=pk)
    form = forms.LevelForm(request.POST or None, instance=lv, event=event)
    if request.method == "POST" and form.is_valid():
        services.save_level(form.save(commit=False), actor=request.user, request=request)
        messages.success(request, _("Level saved."))
        return redirect("announcements:levels", slug)
    return render(request, "announcements/level.html", {"event": event, "form": form, "level": lv})


@ann_view("announcements.view")
def templates(request, slug, *, event):
    return render(request, "announcements/templates.html", {
        "event": event, "templates": Template.objects.filter(event=event).select_related("level", "layout"),
        "can_manage": _any(request, event, "announcements.manage"), "can_compose": _can_compose(request, event)})


@ann_view("announcements.manage")
def template(request, slug, pk=None, *, event):
    tpl = get_object_or_404(Template, event=event, pk=pk) if pk else Template(event=event)
    form = forms.TemplateForm(request.POST or None, instance=tpl, event=event)
    if request.method == "POST":
        if request.POST.get("action") == "delete" and pk:
            services.delete_template(tpl, actor=request.user, request=request)
            messages.success(request, _("Template deleted."))
            return redirect("announcements:templates", slug)
        if form.is_valid():
            services.save_template(form.save(commit=False), actor=request.user, request=request)
            messages.success(request, _("Template saved."))
            return redirect("announcements:templates", slug)
    return render(request, "announcements/template.html", {"event": event, "form": form, "tpl": tpl,
                                                           "is_saved": bool(pk)})


# ------------------------------------------------------------------ public feed
def _feed_event(slug) -> Event:
    event = get_object_or_404(Event, slug=slug)
    if not modules.is_enabled("announcements", event) or not services.ann_settings(event).get("public_feed"):
        raise Http404
    return event


def feed(request, slug):
    event = _feed_event(slug)
    with timezone.override(_tz(event)):
        return render(request, "announcements/feed.html", {
            "event": event, "items": services.feed_items(event), "title": services.feed_title(event)})


def feed_json(request, slug):
    event = _feed_event(slug)
    base = request.build_absolute_uri("/")[:-1]
    items = [{"id": str(a.pk), "title": a.title, "content_text": a.text, "summary": a.short_text,
              "date_published": (a.published_at or a.starts_at).isoformat(), "tags": [a.level.key],
              "url": base + _feed_url(event)} for a in services.feed_items(event)]
    resp = JsonResponse({"version": "https://jsonfeed.org/version/1.1", "title": services.feed_title(event),
                         "home_page_url": base + _feed_url(event), "items": items})
    resp["Cache-Control"] = "public, max-age=30"
    return resp


def feed_rss(request, slug):
    event = _feed_event(slug)
    base = request.build_absolute_uri("/")[:-1]
    rss = Rss201rev2Feed(title=services.feed_title(event), link=base + _feed_url(event),
                         description=_("Announcements of %(e)s") % {"e": event.name}, language="en")
    for a in services.feed_items(event):
        rss.add_item(title=f"{a.level.name}: {a.title}", link=base + _feed_url(event) + f"#a-{a.pk}",
                     description=a.text, unique_id=str(a.pk), pubdate=a.published_at or a.starts_at,
                     categories=[a.level.key])
    from django.http import HttpResponse

    resp = HttpResponse(content_type="application/rss+xml; charset=utf-8")
    rss.write(resp, "utf-8")
    resp["Cache-Control"] = "public, max-age=30"
    return resp


def _feed_url(event) -> str:
    from django.urls import reverse

    return reverse("announcements_public:feed", args=[event.slug])

