# SPDX-License-Identifier: AGPL-3.0-or-later
"""Layout pages: list, details with versions/publishing, the editor island and its JSON endpoints."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.middleware import allow_code_frames
from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import files, forms, layout_format, services
from . import tokens as tok
from .models import Asset, Layout, LayoutVersion, owner_q

#: every string the editor shows (frontend/src/editor uses them as keys; a test keeps both in sync)
EDITOR_STRINGS = [
    # safety signs and checks (ADR-0033)
    "Ahead", "Ahead left", "Ahead right", "Automatic (the screen's way out)", "Back left",
    "Back right", "Checks", "Direction", "Direction arrow", "E001 Emergency exit (left)",
    "E002 Emergency exit (right)", "E003 First aid", "E007 Assembly point", "Not published.",
    "Safety sign", "Sign", "W001 General warning",
    "Data widget", "Widget",
    # program element (ADR-0038)
    "Program", "Show", "Now and next", "The day's sessions", "Live changes", "Stage",
    "Automatic: the screen's room, else all stages", "Rows", "Heading",
    "Add", "Text", "Rich text", "Image", "Slideshow", "Video", "Audio", "Shape", "QR code", "Clock", "Countdown",
    "Date", "Layers", "Properties", "Layout", "Width", "Height", "Background", "Background image", "None",
    "Undo", "Redo", "Delete", "Duplicate", "Bring forward", "Send backward", "Save", "Saving…", "Saved",
    "Unsaved changes", "Publish", "Published", "Back", "Zoom", "Fit", "Name", "Position and size", "X", "Y",
    "Rotation", "Content", "Style", "Colour", "Font", "Font size", "Weight", "Alignment", "Left", "Center",
    "Right", "Justify", "Vertical", "Top", "Middle", "Bottom", "Line height", "Letter spacing", "Text case",
    "Padding", "Corner radius", "Border", "Border colour", "Opacity", "Shadow", "Tabular numbers", "Animation",
    "Entrance", "Fade", "Slide up", "Slide in", "Zoom in", "Duration (ms)", "Delay (ms)", "Show only if",
    "Hidden", "Locked", "Shrink text to fit", "Maximum lines", "Ticker (scrolling)", "File", "Fit mode",
    "Cover", "Contain", "Stretch", "Images", "Seconds per image", "Loop", "Muted", "Form", "Rectangle",
    "Ellipse", "Line", "Format", "Time zone (empty = event)", "Target time", "Text when finished", "Custom",
    "Primary", "Accent", "Muted text", "Surface", "Success", "Warning", "Danger", "Body font", "Heading font",
    "Normal", "Italic", "Style of text", "Uppercase", "Lowercase", "Capitalise", "No selection",
    "Select an element on the canvas or in the layers list.", "Several elements selected", "Align left",
    "Align centre", "Align right", "Align top", "Align middle", "Align bottom",
    "Someone else saved this layout in the meantime.", "The layout could not be saved.",
    "Template variables: {{ event.name }}, {{ screen.name }}, {{ screen.zone }}, {{ now|time }}",
    "Seconds on screen (playlists)", "Upload files", "Long", "Short", "Weekday", "ISO", "Automatic",
    "Hours:minutes:seconds", "Minutes:seconds", "Days", "Rendering error", "Element",
    "Code", "HTML", "CSS", "JavaScript", "Data for the code", "Event", "Screen", "Time", "Files",
    "Only people allowed to write code can change this element.",
    ("Code runs in a sandbox without network. Read data with evac.data and evac.onData(fn); evac.now() is the "
     "server time."),
]


def _layout(event, pk) -> Layout:
    return get_object_or_404(Layout.objects.filter(event=event).select_related("published", "theme"), pk=pk)


def _perm(request, event, perm) -> bool:
    return rbac.has_perm(request.user, event, perm, request=request)


@event_view("content.view", module="content")
def layouts(request, slug, *, event):
    can_edit = _perm(request, event, "content.edit")
    form = forms.LayoutCreateForm(request.POST or None, event=event, prefix="new") if can_edit else None
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            w, h = form.cleaned_data["size"]
            layout = services.create_layout(event, name=form.cleaned_data["name"], key=form.key(), actor=request.user,
                                            request=request, width=w, height=h,
                                            starter=form.cleaned_data["starter"])
            return redirect("content:layout_edit", slug, layout.pk)
    return render(request, "content/layouts.html", {
        "event": event, "layouts": Layout.objects.filter(event=event).select_related("published", "updated_by"),
        "form": form,
    })


@event_view("content.view", module="content")
def layout(request, slug, pk, *, event):
    obj = _layout(event, pk)
    can_edit, can_publish = _perm(request, event, "content.edit"), _perm(request, event, "content.publish")
    meta = forms.LayoutMetaForm(request.POST or None, instance=obj, event=event, prefix="meta") if can_edit else None
    publish_form = forms.PublishForm(request.POST or None, prefix="pub") if can_publish else None
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("publish", "publish_version"):
            if not can_publish:
                raise PermissionDenied
            version = (get_object_or_404(LayoutVersion, layout=obj, pk=request.POST.get("version"))
                       if action == "publish_version" else None)
            at = publish_form.cleaned_data.get("at") if publish_form.is_valid() else None
            v = services.publish_layout(obj, actor=request.user, request=request, version=version, at=at)
            messages.success(request, _("Version %(n)s scheduled.") % {"n": v.number} if v.publish_at
                             else _("Version %(n)s is live on the screens.") % {"n": v.number})
        elif not can_edit:
            raise PermissionDenied
        elif action == "rollback":
            version = get_object_or_404(LayoutVersion, layout=obj, pk=request.POST.get("version"))
            services.rollback_layout(obj, version, actor=request.user, request=request)
            messages.success(request, _("Version %(n)s restored as the draft. Publish it to show it on the screens.")
                             % {"n": version.number})
        elif action == "default":
            services.set_default_layout(event, obj, actor=request.user, request=request)
            messages.success(request, _("Screens show this layout by default."))
        elif action == "delete":
            services.delete_layout(obj, actor=request.user, request=request)
            messages.success(request, _("Layout deleted."))
            return redirect("content:layouts", slug)
        elif meta.is_valid():
            meta.save()
            messages.success(request, _("Saved."))
        return redirect("content:layout", slug, obj.pk)
    versions = list(obj.versions.select_related("created_by")[:30])
    for newer, older in zip(versions, versions[1:] + [None], strict=False):
        newer.diff = layout_format.summary_diff(older.data if older else {}, newer.data)
    return render(request, "content/layout.html", {
        "event": event, "layout": obj, "meta": meta, "publish_form": publish_form, "versions": versions,
        "can_edit": can_edit, "can_publish": can_publish,
    })


def editor_config(request, event, obj: Layout) -> dict:
    assets = Asset.objects.filter(owner_q(event), status=Asset.Status.READY).order_by("name")
    theme = obj.theme or services.event_theme(event)
    values = services.resolved_tokens(theme)
    images = {str(a.pk): files.asset_url(a, a.variant("webp", "original"))
              for a in assets if str(a.pk) in tok.referenced_assets(values)}
    return {
        "layout": {"id": str(obj.pk), "name": obj.name, "data": obj.data, "version": obj.version},
        "assets": {str(a.pk): services.asset_entry(a, files.portal_url) for a in assets},
        "fonts": services.font_stacks(event),
        "fontChoices": [{"value": v, "label": str(label)} for v, label in services.font_choices(event)
                        if v != "system"],
        "themeVariables": tok.css_variables(values, families=services.font_stacks(event), urls=images),
        "vars": {"event": {"name": event.name, "slug": event.slug},
                 "screen": {"name": "Screen", "zone": "Zone", "room": "Room", "venue": "Venue", "tags": []},
                 # sample values for evacuation layouts (ADR-0033); screens fill in their own
                 "evac": {"stage": "Evacuate", "text": "Please leave the building now via the nearest exit.",
                          "direction": "Exit East", "target": "Assembly point Meadow", "arrow": "ahead_left",
                          "drill": ""}},
        "timezone": event.timezone,
        "urls": {"save": reverse("content:layout_save", args=[event.slug, obj.pk]),
                 "publish": reverse("content:layout_publish", args=[event.slug, obj.pk]),
                 "back": reverse("content:layout", args=[event.slug, obj.pk]),
                 "assets": reverse("content:assets", args=[event.slug])},
        "canPublish": _perm(request, event, "content.publish"),
        "canCode": services.may_write_code(request.user, event, request),
        "types": list(layout_format.ELEMENT_TYPES),
        "choices": editor_choices(event),
        "findings": services.layout_findings(obj),
    }


def editor_choices(event) -> dict:
    """Choices other modules offer to the editor (custom widgets for "data" elements, ...)."""
    from apps.core import modules
    from apps.core.registry import registry

    return {key: fn(event) for key, (module, fn) in registry.ensure_loaded().editor_choices_.items()
            if module == "core" or modules.is_enabled(module, event)}


EDITOR_DIR = Path(settings.BASE_DIR) / "static" / "editor"


@lru_cache(maxsize=1)
def editor_version() -> str:
    h = hashlib.sha256()
    for name in ("editor.js", "editor.css", "preview.js", "preview.css"):
        p = EDITOR_DIR / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def editor_strings() -> dict[str, str]:
    """UI strings of the editor (English source text -> translation); the editor falls back to the key."""
    return {s: _(s) for s in EDITOR_STRINGS}


@event_view("content.edit", module="content")
def layout_edit(request, slug, pk, *, event):
    obj = _layout(event, pk)
    other = services.mark_editing(obj, request.user)
    return allow_code_frames(render(request, "content/layout_edit.html", {
        "event": event, "layout": obj, "config": editor_config(request, event, obj), "other_editor": other,
        "strings": editor_strings(), "editor_version": editor_version(),
    }))


def _json(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@require_POST
@event_view("content.edit", module="content")
def layout_save(request, slug, pk, *, event):
    obj = _layout(event, pk)
    body = _json(request)
    try:
        services.save_layout(obj, body.get("data"), actor=request.user, request=request,
                             expected_version=body.get("version"), note=str(body.get("note") or ""))
    except services.Conflict as exc:
        return JsonResponse({"ok": False, "conflict": True, "error": exc.messages[0]}, status=409)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)
    services.mark_editing(obj, request.user)
    return JsonResponse({"ok": True, "version": obj.version, "saved_at": timezone.now().isoformat(),
                         "findings": services.layout_findings(obj)})


@require_POST
@event_view("content.publish", module="content")
def layout_publish(request, slug, pk, *, event):
    obj = _layout(event, pk)
    try:
        version = services.publish_layout(obj, actor=request.user, request=request)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages, "findings": services.layout_findings(obj)},
                            status=400)
    return JsonResponse({"ok": True, "published": version.number})
