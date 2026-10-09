# SPDX-License-Identifier: AGPL-3.0-or-later
"""Portal pages: design overview, themes (token editor with preview), fonts, asset library; file views."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST, require_safe

from apps.core import settings_schema
from apps.core.forms import SchemaForm
from apps.events import rbac
from apps.portal.shortcuts import event_view

from . import files, forms, services
from . import tokens as tok
from .models import Asset, AssetFolder, FontFamily, Theme, owner_q


def _can_edit(request, event) -> bool:
    return rbac.has_perm(request.user, event, "content.edit", request=request)


def _owner(request, event, form) -> object:
    """The event, or None (shared library) when an instance admin ticked "shared"."""
    return None if request.user.is_superuser and form.cleaned_data.get("shared") else event


def _check_writable(request, event, obj) -> None:
    if obj.event_id is None:
        if not request.user.is_superuser:
            raise PermissionDenied(_("Only instance admins change the shared library."))
    elif obj.event_id != event.pk or not _can_edit(request, event):
        raise PermissionDenied


def _preview_css(event, theme) -> str:
    values = services.resolved_tokens(theme)
    images = {str(a.pk): files.asset_url(a, a.variant("webp", "original"))
              for a in Asset.objects.filter(owner_q(event), pk__in=[v for v in tok.referenced_assets(values)
                                                                    if services._is_uuid(v)])}
    return tok.css_block(tok.css_variables(values, families=services.font_stacks(event), urls=images),
                         ".theme-preview")


@event_view("content.view", module="content")
def index(request, slug, *, event):
    theme = services.event_theme(event)
    return render(request, "content/index.html", {
        "event": event, "theme": theme, "preview_css": _preview_css(event, theme),
        "counts": {"layouts": event.layouts.count(), "themes": Theme.objects.filter(owner_q(event)).count(),
                   "fonts": FontFamily.objects.filter(owner_q(event)).count(),
                   "assets": Asset.objects.filter(owner_q(event)).count()},
    })


# --------------------------------------------------------------------------- themes

@event_view("content.view", module="content")
def themes(request, slug, *, event):
    can_edit = _can_edit(request, event)
    form = forms.ThemeForm(request.POST or None, event=event, prefix="new") if can_edit else None
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            theme = form.save(commit=False)
            theme.event = event
            services.save_theme(theme, actor=request.user, request=request)
            messages.success(request, _("Theme created. Adjust its tokens below."))
            return redirect("content:theme", slug, theme.pk)
    return render(request, "content/themes.html", {"event": event, "themes": services.themes(event), "form": form,
                                                   "current": services.event_theme(event)})


@event_view("content.view", module="content")
def theme(request, slug, pk, *, event):
    obj = get_object_or_404(Theme.objects.filter(owner_q(event)), pk=pk)
    writable = _can_edit(request, event) and (obj.event_id == event.pk or request.user.is_superuser)
    schema = services.theme_schema(event)
    parent_values = obj.parent.resolved() if obj.parent_id else None
    resolved = settings_schema.resolve(schema, [("parent", parent_values or {}), ("theme", obj.tokens or {})])
    meta = forms.ThemeForm(request.POST or None, instance=obj, event=event, prefix="meta") if writable else None
    tokens_form = SchemaForm(request.POST or None, schema=schema, initial_values=obj.tokens or {}, inherit=True,
                             resolved=resolved, level="theme", prefix="tok") if writable else None
    if request.method == "POST":
        if not writable:
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "delete":
            try:
                services.delete_theme(obj, actor=request.user, request=request)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect("content:theme", slug, obj.pk)
            messages.success(request, _("Theme deleted."))
            return redirect("content:themes", slug)
        if action == "default":
            services.set_event_theme(event, obj, actor=request.user, request=request)
            messages.success(request, _("Screens of this event now use this theme."))
            return redirect("content:theme", slug, obj.pk)
        if meta.is_valid() and tokens_form.is_valid():
            try:
                services.save_theme(meta.save(commit=False), actor=request.user, request=request,
                                    tokens=tokens_form.values(), schema=schema,
                                    expected_version=int(request.POST.get("version") or 0))
            except services.Conflict as exc:
                messages.error(request, exc.messages[0])
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                messages.success(request, _("Theme saved."))
                return redirect("content:theme", slug, obj.pk)
    return render(request, "content/theme.html", {
        "event": event, "theme": obj, "meta": meta, "tokens_form": tokens_form, "writable": writable,
        "preview_css": _preview_css(event, obj), "is_default": event.default_theme == obj.key,
        "fonts_css_url": "fonts.css",
    })


# --------------------------------------------------------------------------- fonts

@event_view("content.view", module="content")
def fonts(request, slug, *, event):
    can_edit = _can_edit(request, event)
    form = forms.FontUploadForm(request.POST or None, request.FILES or None, event=event, user=request.user,
                                prefix="font") if can_edit else None
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            d = form.cleaned_data
            try:
                ff = services.upload_font(_owner(request, event, form), d["file"], actor=request.user,
                                          request=request, family=d["family"], name=d["name"],
                                          category=d["category"], licence=d["licence"], subset=d["subset"])
            except ValidationError as exc:
                form.add_error("file", exc.messages[0])
            else:
                messages.success(request, _("Font added: %(name)s %(w)s %(s)s.") % {
                    "name": ff.family.name, "w": ff.weight_label, "s": ff.style})
                return redirect("content:fonts", slug)
    return render(request, "content/fonts.html", {"event": event, "families": services.font_families(event),
                                                  "form": form, "can_edit": can_edit})


@require_POST
@event_view("content.edit", module="content")
def font_delete(request, slug, pk, *, event):
    fam = get_object_or_404(FontFamily.objects.filter(owner_q(event)), pk=pk)
    _check_writable(request, event, fam)
    try:
        services.delete_font_family(fam, actor=request.user, request=request)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, _("Font deleted."))
    return redirect("content:fonts", slug)


@require_safe
@event_view("content.view", module="content")
def fonts_css(request, slug, *, event):
    css = services.fonts_css(event, lambda ff: files.portal_url(ff.sha256, "font.woff2"))
    css += "\n" + "\n".join(f'.font-{f.pk.hex}{{font-family:{f.stack};}}' for f in services.font_families(event))
    resp = HttpResponse(css, content_type="text/css; charset=utf-8")
    resp["Cache-Control"] = "private, no-cache"
    return resp


# --------------------------------------------------------------------------- assets

@event_view("content.view", module="content")
def assets(request, slug, *, event):
    can_edit = _can_edit(request, event)
    upload = (forms.AssetUploadForm(request.POST or None, request.FILES or None, event=event, user=request.user,
                                    prefix="up") if can_edit else None)
    folder_form = forms.FolderForm(request.POST or None, event=event, prefix="folder") if can_edit else None
    if request.method == "POST":
        if not can_edit:
            raise PermissionDenied
        if request.POST.get("action") == "folder":
            if folder_form.is_valid():
                folder = folder_form.save(commit=False)
                folder.event = event
                folder.save()
                messages.success(request, _("Folder created."))
                return redirect(f"{request.path}?folder={folder.pk}")
        elif upload.is_valid():
            owner = _owner(request, event, upload)
            added, errors = 0, []
            for f in upload.cleaned_data["files"]:
                try:
                    _asset, created = services.upload_asset(owner, f, actor=request.user, request=request,
                                                            folder=upload.cleaned_data["folder"],
                                                            tags=upload.cleaned_data["tags"])
                    added += int(created)
                except ValidationError as exc:
                    errors.append(f"{f.name}: {exc.messages[0]}")
            for e in errors:
                messages.error(request, e)
            if added:
                messages.success(request, _("%(n)d file(s) added. Videos are converted in the background.") %
                                 {"n": added})
            return redirect(request.get_full_path())
    qs = Asset.objects.filter(owner_q(event)).select_related("folder")
    folder = None
    if request.GET.get("folder"):
        folder = AssetFolder.objects.filter(owner_q(event), pk=request.GET["folder"]).first()
        qs = qs.filter(folder=folder) if folder else qs
    kind = request.GET.get("kind", "")
    if kind in Asset.Kind.values:
        qs = qs.filter(kind=kind)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(original_name__icontains=q) | Q(alt_text__icontains=q))
    tag = request.GET.get("tag", "").strip().lower()
    items = [a for a in qs[:500] if not tag or tag in (a.tags or [])]
    return render(request, "content/assets.html", {
        "event": event, "assets": items, "upload": upload, "folder_form": folder_form, "can_edit": can_edit,
        "folders": AssetFolder.objects.filter(owner_q(event)), "folder": folder, "kinds": Asset.Kind.choices,
        "kind": kind, "q": q, "tag": tag,
    })


@event_view("content.view", module="content")
def asset(request, slug, pk, *, event):
    obj = get_object_or_404(Asset.objects.filter(owner_q(event)), pk=pk)
    writable = _can_edit(request, event) and (obj.event_id == event.pk or request.user.is_superuser)
    form = forms.AssetForm(request.POST or None, instance=obj, event=event, prefix="asset") if writable else None
    if request.method == "POST":
        if not writable:
            raise PermissionDenied
        action = request.POST.get("action")
        if action == "delete":
            try:
                services.delete_asset(obj, actor=request.user, request=request)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect("content:asset", slug, obj.pk)
            messages.success(request, _("File deleted."))
            return redirect("content:assets", slug)
        if action == "reprocess":
            from .tasks import process_asset

            Asset.objects.filter(pk=obj.pk).update(status=Asset.Status.PROCESSING)
            process_asset.delay(str(obj.pk))
            messages.success(request, _("Processing again."))
            return redirect("content:asset", slug, obj.pk)
        before = {f: getattr(obj, f) for f in ("name", "alt_text", "credit", "tags", "folder")}
        if form.is_valid():
            services.save_asset(form.save(commit=False), actor=request.user, request=request, before=before)
            messages.success(request, _("Saved."))
            return redirect("content:asset", slug, obj.pk)
    variants = [{"name": k, **v, "url": files.portal_url(obj.sha256, v["file"])} for k, v in obj.variants.items()]
    return render(request, "content/asset.html", {
        "event": event, "asset": obj, "form": form, "writable": writable, "variants": variants,
        "usage": services.asset_usage(obj),
        "preview": files.asset_url(obj, obj.variant("webp", "mp4", "audio", "original")),
        "poster": files.asset_url(obj, "poster") if obj.variant("poster") else "",
    })


# --------------------------------------------------------------------------- files

@require_safe
def file(request, sha, name):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if not files.user_may_read(request.user, sha, request=request):
        raise Http404
    return files.respond(sha, name)
