# SPDX-License-Identifier: AGPL-3.0-or-later
"""Files, fonts, themes and layouts in ``.evacpack`` files (ADR-0024). Imports go through the content services,
so every created object is validated and audit-logged like a manual upload; layouts with code still need
``content.code``."""
from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.files import File
from django.utils.translation import gettext as _

from . import layout_format as lf
from . import services, storage
from . import tokens as tok
from .models import Asset, FontFamily, Layout, Theme, owner_q


def _errors(exc: ValidationError) -> str:
    return "; ".join(str(m) for m in exc.messages)[:300]


def unique(exists, base: str, *, sep: str = "-", limit: int = 64) -> str:
    """``base``, else ``base-2``, ``base-3`` … (``exists(value) -> bool``)."""
    value, n = base[:limit], 2
    while exists(value):
        suffix = f"{sep}{n}" if sep == "-" else f" ({n})"
        value = f"{base[:limit - len(suffix)]}{suffix}"
        n += 1
    return value


def _is_uuid(value: Any) -> bool:
    return isinstance(value, str) and services._is_uuid(value)


# ------------------------------------------------------------------ files (assets)
def asset_choices(event) -> list[tuple[str, str]]:
    return [(str(pk), name) for pk, name in Asset.objects.filter(owner_q(event)).values_list("pk", "name")]


def dump_assets(event, ids: set[str], files) -> list[dict[str, Any]]:
    out = []
    for a in Asset.objects.filter(owner_q(event), pk__in=ids).order_by("name"):
        original = (a.variants or {}).get("original", {}).get("file")
        src = storage.path(a.sha256, original) if original else None
        if src is None or not src.exists():
            continue
        out.append({"id": str(a.pk), "name": a.name, "kind": a.kind, "original_name": a.original_name,
                    "alt_text": a.alt_text, "credit": a.credit, "tags": a.tags,
                    "file": files.add(src, a.original_name or original)})
    return out


def load_assets(event, items: list[dict[str, Any]], ctx) -> list[str]:
    created = []
    for item in items:
        name = str(item.get("name") or "")[:200]
        try:
            path = ctx.file(item.get("file"))
            with open(path, "rb") as fh:
                asset, new = services.upload_asset(event, File(fh, name=str(item.get("original_name") or name)),
                                                   actor=ctx.actor, request=ctx.request, tags=item.get("tags") or (),
                                                   name=name)
        except ValidationError as exc:
            ctx.warn(_("File %(name)s skipped: %(error)s") % {"name": name, "error": _errors(exc)})
            continue
        if new and (item.get("alt_text") or item.get("credit")):
            asset.alt_text = str(item.get("alt_text") or "")[:300]
            asset.credit = str(item.get("credit") or "")[:300]
            services.save_asset(asset, actor=ctx.actor, request=ctx.request)
        ctx.ids[str(item["id"])] = str(asset.pk)
        if new:
            created.append(asset.name)
    return created


# ------------------------------------------------------------------ fonts
def font_choices(event) -> list[tuple[str, str]]:
    return [(str(f.pk), f.name) for f in services.font_families(event)]


def dump_fonts(event, ids: set[str], files) -> list[dict[str, Any]]:
    out = []
    for fam in FontFamily.objects.filter(owner_q(event), pk__in=ids).prefetch_related("files").order_by("name"):
        if fam.builtin:
            out.append({"id": str(fam.pk), "name": fam.name, "builtin": True})
            continue
        packed = [{"file": files.add(src, f"{fam.name}-{ff.weight_label}-{ff.style}.woff2")}
                  for ff in fam.files.all() if (src := storage.path(ff.sha256, "font.woff2")).exists()]
        out.append({"id": str(fam.pk), "name": fam.name, "category": fam.category, "licence": fam.licence,
                    "files": packed})
    return out


def load_fonts(event, items: list[dict[str, Any]], ctx) -> list[str]:
    created = []
    for item in items:
        name = str(item.get("name") or "")[:120]
        if item.get("builtin"):
            fam = FontFamily.objects.filter(builtin=True, name__iexact=name).first()
            if fam:
                ctx.ids[str(item["id"])] = str(fam.pk)
            else:
                ctx.warn(_("Built-in font %(name)s is not available here; the theme font is used instead.")
                         % {"name": name})
            continue
        family = None
        for f in item.get("files") or []:
            try:
                with open(ctx.file(f.get("file")), "rb") as fh:
                    ff = services.upload_font(event, File(fh, name=f"{name}.woff2"), actor=ctx.actor,
                                              request=ctx.request, family=family, name=name,
                                              category=str(item.get("category") or FontFamily.Category.SANS),
                                              licence=str(item.get("licence") or ""))
            except ValidationError as exc:
                ctx.warn(_("Font %(name)s: a file was skipped (%(error)s).") % {"name": name, "error": _errors(exc)})
                continue
            family = ff.family
        if family is None:
            ctx.warn(_("Font %(name)s skipped: no usable file.") % {"name": name})
            continue
        ctx.ids[str(item["id"])] = str(family.pk)
        created.append(family.name)
    return created


# ------------------------------------------------------------------ themes
def theme_choices(event) -> list[tuple[str, str]]:
    return [(str(t.pk), t.name) for t in services.themes(event)]


def _theme_refs(tokens: dict[str, Any]) -> tuple[set[str], set[str]]:
    fonts = {str(tokens[k]) for k in ("font_body", "font_heading") if _is_uuid(tokens.get(k))}
    return {a for a in tok.referenced_assets(tokens) if _is_uuid(a)}, fonts


def theme_requires(event, ids: set[str]) -> dict[str, set[str]]:
    assets, fonts, parents = set(), set(), set()
    for t in Theme.objects.filter(owner_q(event), pk__in=ids):
        a, f = _theme_refs(t.tokens or {})
        assets |= a
        fonts |= f
        if t.parent_id:
            parents.add(str(t.parent_id))
    return {"assets": assets, "fonts": fonts, "themes": parents}


def dump_themes(event, ids: set[str], files) -> list[dict[str, Any]]:
    rows = list(Theme.objects.filter(owner_q(event), pk__in=ids))
    rows.sort(key=lambda t: (len(t.chain()), t.name))  # parents first
    return [{"id": str(t.pk), "key": t.key, "name": t.name, "description": t.description,
             "parent": str(t.parent_id) if t.parent_id and str(t.parent_id) in ids else None, "tokens": t.tokens}
            for t in rows]


def load_themes(event, items: list[dict[str, Any]], ctx) -> list[str]:
    created = []
    # pictures imported a moment ago are still being processed: allow them as theme images already
    images = services.image_choices(event)
    images += [(str(pk), name) for pk, name in Asset.objects.filter(
        event=event, kind__in=["image", "svg"], pk__in=list(ctx.ids.values())).exclude(
        status=Asset.Status.READY).values_list("pk", "name")]
    schema = tok.schema(fonts=services.font_choices(event), images=images)
    for item in items:
        name = str(item.get("name") or "")[:200]
        tokens = ctx.remap(dict(item.get("tokens") or {}))
        for key, value in list(tokens.items()):
            if key in ("font_body", "font_heading", "background_image", "logo") and _is_uuid(value) \
                    and value not in ctx.ids.values():
                del tokens[key]
        parent = Theme.objects.filter(owner_q(event), pk=ctx.ids.get(str(item.get("parent")))).first() \
            if item.get("parent") else None
        key = unique(lambda k: Theme.objects.filter(event=event, key=k).exists(),
                     str(item.get("key") or "imported")[:64] or "imported")
        try:
            theme = services.save_theme(Theme(event=event, key=key, name=name or key,
                                              description=str(item.get("description") or "")[:2000],
                                              parent=parent),
                                        actor=ctx.actor, request=ctx.request, tokens=tokens, schema=schema)
        except ValidationError as exc:
            ctx.warn(_("Theme %(name)s skipped: %(error)s") % {"name": name, "error": _errors(exc)})
            continue
        ctx.ids[str(item["id"])] = str(theme.pk)
        created.append(theme.name)
    return created


# ------------------------------------------------------------------ layouts
def layout_choices(event) -> list[tuple[str, str]]:
    return [(str(pk), name) for pk, name in Layout.objects.filter(owner_q(event)).values_list("pk", "name")]


def _prop_ids(data: dict[str, Any]) -> set[str]:
    """UUIDs in element properties (objects of other modules, e.g. custom widgets)."""
    out: set[str] = set()

    def walk(value: Any) -> None:
        if _is_uuid(value):
            out.add(value)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)

    for el in data.get("elements", []):
        walk(el.get("props") or {})
    return out


def layout_requires(event, ids: set[str]) -> dict[str, set[str]]:
    assets, fonts, themes, other = set(), set(), set(), set()
    for layout in Layout.objects.filter(owner_q(event), pk__in=ids):
        data = layout.data or {}
        assets |= lf.asset_ids(data)
        fonts |= lf.font_ids(data)
        other |= _prop_ids(data)
        if layout.theme_id:
            themes.add(str(layout.theme_id))
    return {"assets": assets, "fonts": fonts, "themes": themes, "*": other - assets}


def dump_layouts(event, ids: set[str], files) -> list[dict[str, Any]]:
    return [{"id": str(x.pk), "key": x.key, "name": x.name, "description": x.description,
             "theme": str(x.theme_id) if x.theme_id else None, "published": bool(x.published_id), "data": x.data}
            for x in Layout.objects.filter(owner_q(event), pk__in=ids).order_by("name")]


def load_layouts(event, items: list[dict[str, Any]], ctx) -> list[str]:
    created = []
    for item in items:
        name = str(item.get("name") or "")[:200] or _("Imported layout")
        data = ctx.remap(item.get("data") or {})
        for el in data.get("elements", []) if isinstance(data, dict) else []:
            style = el.get("style") if isinstance(el, dict) else None
            if isinstance(style, dict) and _is_uuid(style.get("fontFamily")) \
                    and style["fontFamily"] not in ctx.ids.values():
                style["fontFamily"] = "token:body"
        key = unique(lambda k: Layout.objects.filter(event=event, key=k).exists(),
                     str(item.get("key") or "imported")[:64] or "imported")
        try:
            layout = services.create_layout(event, name=name, key=key, actor=ctx.actor, request=ctx.request,
                                            data=data)
        except ValidationError as exc:
            ctx.warn(_("Layout %(name)s skipped: %(error)s") % {"name": name, "error": _errors(exc)})
            continue
        theme_id = ctx.ids.get(str(item.get("theme"))) if item.get("theme") else None
        if theme_id:
            layout.theme = Theme.objects.filter(owner_q(event), pk=theme_id).first()
            layout.save(update_fields=["theme", "updated_at"])
        if item.get("published"):
            services.publish_layout(layout, actor=ctx.actor, request=ctx.request)
        ctx.ids[str(item["id"])] = str(layout.pk)
        created.append(layout.name)
    return created
