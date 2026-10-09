# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data feeds and the no-code widget builder (ADR-0023)."""
from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.content.layout_views import editor_version
from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import forms, mapping, services, tasks
from .models import CustomWidget, Feed


def _can_edit(request, event) -> bool:
    return rbac.has_perm(request.user, event, "widgets.edit", request=request)


def _fail(request, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


@event_view("widgets.view", module="widgets")
def index(request, slug, *, event):
    return render(request, "widgets/index.html", {
        "event": event, "can_edit": _can_edit(request, event),
        "feeds": Feed.objects.filter(event=event).prefetch_related("widgets"),
        "widgets": CustomWidget.objects.filter(event=event).select_related("feed"),
    })


@event_view("widgets.view", module="widgets")
def feed(request, slug, pk=None, *, event):
    obj = get_object_or_404(Feed, event=event, pk=pk) if pk else Feed(event=event)
    can_edit = _can_edit(request, event)
    form = forms.FeedForm(request.POST or None, instance=obj, event=event)
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            f = form.save(commit=False)
            try:
                services.save_feed(f, actor=request.user, request=request, auth_header=form.auth_value())
            except ValidationError as err:
                _fail(request, err)
            else:
                tasks.fetch_feed.delay(str(f.pk))
                messages.success(request, _("Feed saved; fetching it now."))
                return redirect("widgets:feed", slug, f.pk)
    tree = mapping.tree(obj.snapshot) if obj.snapshot is not None else None
    return render(request, "widgets/feed.html", {"event": event, "feed": obj, "form": form, "tree": tree,
                                                 "can_edit": can_edit, "is_saved": not obj._state.adding})


@require_POST
@event_view("widgets.edit", module="widgets")
def feed_fetch(request, slug, pk, *, event):
    obj = get_object_or_404(Feed, event=event, pk=pk)
    tasks.fetch_feed.delay(str(obj.pk))
    messages.info(request, _("Fetching the feed."))
    return redirect("widgets:feed", slug, obj.pk)


@require_POST
@event_view("widgets.edit", module="widgets")
def feed_delete(request, slug, pk, *, event):
    obj = get_object_or_404(Feed, event=event, pk=pk)
    try:
        services.delete_feed(obj, actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
        return redirect("widgets:feed", slug, obj.pk)
    messages.success(request, _("Feed deleted."))
    return redirect("widgets:index", slug)


def _preview_config(event, w: CustomWidget) -> dict:
    """Render the widget with the screen renderer (preview island) in a 16:9 frame."""
    from apps.content import services as content_services
    from apps.content import tokens as tok

    values = content_services.resolved_tokens(content_services.event_theme(event))
    layout = {"format": 1, "width": 1920, "height": 1080, "background": {"color": "token:background"},
              "elements": [{"id": "w", "type": "data", "name": w.name, "frame": {"x": 4, "y": 6, "w": 92, "h": 88},
                            "style": {"fontSize": 4.5}, "props": {"widget": str(w.pk)}}]}
    return {"layout": layout, "at": 0, "timezone": event.timezone,
            "vars": {"event": {"name": event.name, "slug": event.slug}}, "assets": {},
            "fonts": content_services.font_stacks(event),
            "themeVariables": tok.css_variables(values, families=content_services.font_stacks(event)),
            "data": {str(w.pk): services.widget_payload(w)}}


@event_view("widgets.view", module="widgets")
def widget(request, slug, pk=None, *, event):
    obj = get_object_or_404(CustomWidget.objects.select_related("feed"), event=event, pk=pk) if pk else \
        CustomWidget(event=event)
    if not pk and request.GET.get("feed"):
        obj.feed = Feed.objects.filter(event=event, pk=request.GET["feed"]).first() if len(request.GET["feed"]) == 36 \
            else None
    can_edit = _can_edit(request, event)
    form = forms.WidgetForm(request.POST or None, instance=obj, event=event,
                            initial={"feed": obj.feed_id} if obj.feed_id else None)
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            w = form.build()
            try:
                services.save_widget(w, actor=request.user, request=request)
            except ValidationError as err:
                _fail(request, err)
            else:
                messages.success(request, _("Widget saved. Add it to a layout with the “Data” element."))
                return redirect("widgets:widget", slug, w.pk)
    saved = not obj._state.adding
    return render(request, "widgets/widget.html", {
        "event": event, "w": obj, "form": form, "can_edit": can_edit, "is_saved": saved,
        "rows": services.widget_rows(obj) if saved else [],
        "tree": mapping.tree(obj.feed.snapshot) if saved and obj.feed.snapshot is not None else None,
        "config": _preview_config(event, obj) if saved else None, "editor_version": editor_version(),
        "row_fields": mapping.FIELDS,
    })


@require_POST
@event_view("widgets.edit", module="widgets")
def widget_delete(request, slug, pk, *, event):
    obj = get_object_or_404(CustomWidget, event=event, pk=pk)
    services.delete_widget(obj, actor=request.user, request=request)
    messages.success(request, _("Widget deleted."))
    return redirect("widgets:index", slug)
