# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screen packs: gallery, export, import with review (ADR-0024) and the instance's pack keys."""
from __future__ import annotations

import re
import time

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.content.layout_views import editor_version
from apps.core import modules
from apps.events import rbac
from apps.portal.shortcuts import event_view, superuser_view

from . import engine, forms, gallery, packfile, services
from .models import PackImport, TrustedKey


def _perms(request, event) -> tuple[bool, bool]:
    return (rbac.has_perm(request.user, event, "packs.import", request=request),
            rbac.has_perm(request.user, event, "packs.export", request=request))


def _fail(request, err: ValidationError) -> None:
    for m in err.messages:
        messages.error(request, m)


def _titles() -> dict[str, str]:
    return {s.key: s.title for s in engine.sections()}


def _summary(contents: dict) -> list[tuple[str, list[str]]]:
    titles = _titles()
    return [(titles.get(k, k), [i.get("name") or "–" for i in items]) for k, items in contents.items()]


@event_view(None, module="packs")
def index(request, slug, *, event):
    can_import, can_export = _perms(request, event)
    if not (can_import or can_export):
        raise PermissionDenied("packs.import")
    cards = []
    for entry in gallery.entries().values():
        missing = [m for m in entry.get("modules", []) if not modules.is_enabled(m, event)]
        cards.append({**entry, "summary": _summary({k: v for k, v in entry["sections"].items()}),
                      "missing": missing})
    return render(request, "packs/index.html", {
        "event": event, "can_import": can_import, "can_export": can_export, "gallery": cards,
        "upload_form": forms.UploadForm(), "url_form": forms.UrlForm(),
        "url_import": services.config().get("allow_url_import", True),
        "imports": PackImport.objects.filter(event=event)[:20],
    })


@event_view("packs.export", module="packs")
def export(request, slug, *, event):
    form = forms.ExportForm(request.POST or None, event=event, initial={"name": event.name})
    if request.method == "POST" and form.is_valid():
        try:
            fh = services.export(event, form.selection(), name=form.cleaned_data["name"],
                                 description=form.cleaned_data["description"], sign=form.cleaned_data["sign"],
                                 actor=request.user, request=request)
        except ValidationError as err:
            _fail(request, err)
        else:
            filename = re.sub(r"[^A-Za-z0-9._-]+", "-", form.cleaned_data["name"]).strip("-")[:80] or "pack"
            return FileResponse(fh, as_attachment=True, filename=f"{filename}.evacpack",
                                content_type="application/vnd.evac.pack+zip")
    return render(request, "packs/export.html", {"event": event, "form": form})


@require_POST
@event_view("packs.import", module="packs")
def upload(request, slug, *, event):
    form = forms.UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, _("Choose a pack file."))
        return redirect("packs:index", slug)
    try:
        pi = services.stage_upload(event, form.cleaned_data["file"], actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
        return redirect("packs:index", slug)
    return redirect("packs:review", slug, pi.pk)


@require_POST
@event_view("packs.import", module="packs")
def from_url(request, slug, *, event):
    form = forms.UrlForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Enter a valid URL."))
        return redirect("packs:index", slug)
    try:
        pi = services.stage_url(event, form.cleaned_data["url"], actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
        return redirect("packs:index", slug)
    return redirect("packs:review", slug, pi.pk)


@require_POST
@event_view("packs.import", module="packs")
def from_gallery(request, slug, key, *, event):
    try:
        pi = services.stage_gallery(event, key, actor=request.user, request=request)
    except ValidationError as err:
        _fail(request, err)
        return redirect("packs:index", slug)
    return redirect("packs:review", slug, pi.pk)


def preview_config(event, pack: packfile.Pack) -> dict | None:
    """The pack's first layout in the screen renderer, with the pack's theme and built-in fonts (files inside
    the pack are not shown before the import)."""
    from apps.content import services as content_services
    from apps.content import tokens as tok
    from apps.content.models import FontFamily

    layouts = pack.sections.get("layouts") or []
    if not layouts or not isinstance(layouts[0].get("data"), dict):
        return None
    layout = layouts[0]
    stacks = {}
    for f in pack.sections.get("fonts") or []:
        fam = FontFamily.objects.filter(builtin=True, name__iexact=str(f.get("name") or "")).first() \
            if f.get("builtin") else None
        if fam:
            stacks[str(f["id"])] = fam.stack
    themes = {str(t.get("id")): t for t in pack.sections.get("themes") or []}
    theme = themes.get(str(layout.get("theme"))) or next(iter(themes.values()), None)
    values = content_services.resolved_tokens(None)
    if theme:
        chain, seen = [], set()
        while theme and str(theme.get("id")) not in seen:
            seen.add(str(theme.get("id")))
            chain.insert(0, theme)
            theme = themes.get(str(theme.get("parent")))
        for t in chain:
            values.update({k: v for k, v in (t.get("tokens") or {}).items() if k in values})
    return {"layout": layout["data"], "at": int(time.time() * 1000), "timezone": event.timezone,
            "vars": {"event": {"name": event.name, "slug": event.slug}}, "assets": {}, "fonts": stacks,
            "themeVariables": tok.css_variables(values, families=stacks)}


@event_view("packs.import", module="packs")
def review(request, slug, pk, *, event):
    pi = get_object_or_404(PackImport, event=event, pk=pk)
    if request.method == "POST":
        try:
            result = services.apply(pi, actor=request.user, request=request,
                                    confirmed=request.POST.get("confirm") == "on")
        except ValidationError as err:
            _fail(request, err)
        else:
            count = sum(len(v) for v in result["created"].values())
            messages.success(request, _("Pack imported: %(n)s new items.") % {"n": count})
            return redirect("packs:review", slug, pi.pk)
    pack = missing = config = None
    if pi.status == PackImport.Status.READY:
        try:
            pack = packfile.read(services.staged_path(pi), max_bytes=services.max_bytes())
        except (packfile.PackError, OSError) as exc:
            pi.status, pi.error = PackImport.Status.FAILED, str(exc)
            pi.save(update_fields=["status", "error"])
        else:
            missing = engine.missing_modules(event, pack)
            config = preview_config(event, pack)
    titles = _titles()
    return render(request, "packs/review.html", {
        "event": event, "pi": pi, "summary": _summary(pi.contents), "missing": missing, "config": config,
        "blocked": services.blocked_reason(pi) if pi.status == PackImport.Status.READY else "",
        "confirm": services.needs_confirmation(pi), "fingerprint": packfile.fingerprint(pi.public_key)
        if pi.public_key else "", "editor_version": editor_version(),
        "created": [(titles.get(k, k), v) for k, v in (pi.result.get("created") or {}).items()],
        "warnings": pi.result.get("warnings") or [],
    })


@require_POST
@event_view("packs.import", module="packs")
def discard(request, slug, pk, *, event):
    pi = get_object_or_404(PackImport, event=event, pk=pk)
    services.discard(pi, actor=request.user, request=request)
    messages.success(request, _("Pack discarded."))
    return redirect("packs:index", slug)


# ------------------------------------------------------------------ instance: pack keys
@superuser_view
def keys(request):
    form = forms.TrustForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.trust_key(form.cleaned_data["public_key"], form.cleaned_data["name"], actor=request.user,
                               request=request)
        except ValidationError as err:
            form.add_error("public_key", err)
        else:
            messages.success(request, _("Key trusted."))
            return redirect("packs_admin:keys")
    own = services.own_public_key()
    return render(request, "packs/keys.html", {
        "form": form, "own_key": own, "own_fingerprint": packfile.fingerprint(own),
        "trusted": [(k, packfile.fingerprint(k.public_key)) for k in TrustedKey.objects.all()],
    })


@require_POST
@superuser_view
def untrust(request, pk):
    services.untrust_key(get_object_or_404(TrustedKey, pk=pk), actor=request.user, request=request)
    messages.success(request, _("The key is no longer trusted."))
    return redirect("packs_admin:keys")
