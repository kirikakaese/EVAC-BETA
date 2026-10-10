# SPDX-License-Identifier: AGPL-3.0-or-later
"""State changes of themes, fonts and assets (audit-logged), lookups used by pages, API and player."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from apps.core import settings_schema, settings_store
from apps.core.audit import log

from . import fonts as font_tools
from . import media, storage
from . import tokens as tok
from .models import Asset, AssetFolder, FontFamily, FontFile, Theme, owner_q

logger = logging.getLogger("evac.content")


def content_settings(event=None) -> dict[str, Any]:
    return settings_store.get("content", **({"event": event} if event is not None else {}))


def _tags(value) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    out: list[str] = []
    for t in value or []:
        t = str(t).strip().lower()[:40]
        if t and t not in out:
            out.append(t)
    return out[:30]


# --------------------------------------------------------------------------- fonts

def font_families(event) -> list[FontFamily]:
    return list(FontFamily.objects.filter(owner_q(event)).prefetch_related("files").order_by("-builtin", "name"))


def font_choices(event) -> list[tuple[str, str]]:
    return [("system", _("System UI"))] + [(str(f.pk), f.name) for f in font_families(event)]


def font_stacks(event) -> dict[str, str]:
    return {str(f.pk): f.stack for f in font_families(event)}


@transaction.atomic
def upload_font(event, upload, *, actor, request=None, family: FontFamily | None = None, name: str = "",
                category: str = FontFamily.Category.SANS, licence: str = "", subset: bool = False) -> FontFile:
    max_bytes = 20 * 1024 * 1024
    try:
        tmp, _sha, _size = storage.spool(upload, max_bytes)
    except ValueError as exc:
        raise ValidationError(_("Fonts may be at most 20 MB.")) from exc
    try:
        info = font_tools.read(tmp, upload.name, subset=subset)
    except font_tools.FontError as exc:
        raise ValidationError(str(exc)) from exc
    finally:
        tmp.unlink(missing_ok=True)
    import hashlib

    sha = hashlib.sha256(info.woff2).hexdigest()
    if family is None:
        family = FontFamily.objects.filter(event=event, builtin=False, name__iexact=name or info.family).first()
    if family is None:
        family = FontFamily.objects.create(event=event, name=(name or info.family)[:120], category=category,
                                           licence=licence)
    elif licence and not family.licence:
        family.licence = licence
        family.save(update_fields=["licence", "updated_at"])
    existing = family.files.filter(sha256=sha).first()
    if existing:
        return existing
    storage.write_bytes(sha, "font.woff2", info.woff2)
    ff = FontFile.objects.create(
        family=family, sha256=sha, original_name=upload.name[:200], original_format=info.original_format,
        weight_min=info.weight_min, weight_max=info.weight_max, style=info.style, axes=info.axes,
        unicode_range=info.unicode_range, size=len(info.woff2))
    log(action="font.uploaded", actor=actor, target=family, event=event, request=request,
        message=f"Font {family.name} {ff.weight_label} {ff.style} uploaded ({upload.name})")
    return ff


def delete_font_family(family: FontFamily, *, actor, request=None) -> None:
    if family.builtin:
        raise ValidationError(_("Built-in fonts cannot be deleted."))
    shas = list(family.files.values_list("sha256", flat=True))
    log(action="font.deleted", actor=actor, target=family, event=family.event, request=request,
        message=f"Font {family.name} deleted")
    family.delete()
    for sha in shas:
        _gc(sha)


def fonts_css(event, url_for, only: set[str] | None = None) -> str:
    """@font-face rules for the fonts the event may use (``only``: these family ids); ``url_for(font_file)``
    builds the URL."""
    rules = []
    for fam in font_families(event):
        if only is not None and str(fam.pk) not in only:
            continue
        for ff in fam.files.all():
            url = ff.static_url() or url_for(ff)
            rules.append(font_tools.face_css(fam.css_family, url, weight_min=ff.weight_min,
                                             weight_max=ff.weight_max, style=ff.style,
                                             unicode_range=ff.unicode_range))
    return "\n".join(rules)


# --------------------------------------------------------------------------- assets

def upload_asset(event, upload, *, actor, request=None, folder: AssetFolder | None = None, tags=(),
                 name: str = "") -> tuple[Asset, bool]:
    """Store an upload and queue its processing. Returns ``(asset, created)``; identical files are reused."""
    cfg = content_settings(event)
    try:
        kind, mime, ext = media.classify(upload.name)
    except media.Rejected as exc:
        raise ValidationError(str(exc)) from exc
    try:
        tmp, sha, size = storage.spool(upload, int(cfg["max_upload_mb"]) * 1024 * 1024)
    except ValueError as exc:
        raise ValidationError(_("Files may be at most %(mb)s MB.") % {"mb": cfg["max_upload_mb"]}) from exc
    try:
        existing = Asset.objects.filter(event=event, sha256=sha).first()
        if existing:
            return existing, False
        try:
            meta = media.inspect(kind, tmp)
        except media.Rejected as exc:
            raise ValidationError(str(exc)) from exc
        if kind == "svg":
            try:
                clean = media.sanitize_svg(tmp.read_bytes())
            except Exception as exc:  # noqa: BLE001
                raise ValidationError(_("This SVG file cannot be used.")) from exc
            storage.write_bytes(sha, "original.svg", clean)
            size = len(clean)
        else:
            storage.store(sha, f"original.{ext}", tmp)
    finally:
        tmp.unlink(missing_ok=True)
    asset = Asset.objects.create(
        event=event, folder=folder, name=(name or Path(upload.name).stem)[:200], tags=_tags(tags), kind=kind,
        mime=mime, sha256=sha, original_name=upload.name[:255], extension=ext, size=size,
        width=meta.get("width"), height=meta.get("height"), duration=meta.get("duration"),
        variants={"original": {"file": f"original.{ext}", "mime": mime, "size": size}}, uploaded_by=actor)
    log(action="asset.uploaded", actor=actor, target=asset, event=event, request=request,
        message=f"{asset.get_kind_display()} {asset.name} uploaded ({upload.name}, {size} bytes)")
    from .tasks import process_asset

    transaction.on_commit(lambda: process_asset.delay(str(asset.pk)))
    return asset, True


def process(asset: Asset) -> Asset:
    cfg = content_settings(asset.event)
    src = storage.path(asset.sha256, asset.variants["original"]["file"])
    variants = {"original": asset.variants["original"]}
    note = ""
    try:
        if asset.kind == "image":
            variants.update(media.image_variants(asset.sha256, src, max_px=int(cfg["image_max_px"]),
                                                 avif=bool(cfg["avif"])))
        elif asset.kind in ("video", "audio"):
            if not media.has_ffmpeg():
                note = _("ffmpeg is not installed on this server: the file is used as uploaded.")
            elif asset.kind == "video":
                variants.update(media.video_variants(asset.sha256, src, duration=asset.duration,
                                                     webm=bool(cfg["video_webm"])))
            else:
                variants.update(media.audio_variants(asset.sha256, src))
        asset.status = Asset.Status.READY
    except Exception as exc:  # noqa: BLE001 - keep the asset, show the reason
        logger.exception("processing asset %s failed", asset.pk)
        asset.status, note = Asset.Status.FAILED, str(exc)[:480]
    asset.variants, asset.note = variants, note
    asset.save(update_fields=["variants", "status", "note", "updated_at"])
    return asset


def save_asset(asset: Asset, *, actor, request=None, before: dict | None = None) -> Asset:
    asset.tags = _tags(asset.tags)
    asset.save()
    changes = {k: [v, getattr(asset, k)] for k, v in (before or {}).items() if v != getattr(asset, k)} or None
    log(action="asset.updated", actor=actor, target=asset, event=asset.event, request=request, changes=changes)
    return asset


def asset_usage(asset: Asset) -> list[str]:
    """Where the asset is used: themes and layouts (draft or published version)."""
    from . import layout_format as lf
    from .models import Layout

    key = str(asset.pk)
    scope = Q(event=asset.event) if asset.event_id else Q()
    out = [_("Theme %(name)s") % {"name": t.name} for t in Theme.objects.filter(scope)
           if key in tok.referenced_assets(t.tokens or {})]
    for lay in Layout.objects.filter(scope).select_related("published"):
        if key in lf.asset_ids(lay.data) or (lay.published_id and key in lf.asset_ids(lay.published.data)):
            out.append(_("Layout %(name)s") % {"name": lay.name})
    return out


def delete_asset(asset: Asset, *, actor, request=None) -> None:
    used = asset_usage(asset)
    if used:
        raise ValidationError(_("The file is still used: %(where)s.") % {"where": ", ".join(used)})
    sha = asset.sha256
    log(action="asset.deleted", actor=actor, target=asset, event=asset.event, request=request,
        message=f"Asset {asset.name} deleted")
    asset.delete()
    _gc(sha)


def _gc(sha: str) -> None:
    if not sha or Asset.objects.filter(sha256=sha).exists() or FontFile.objects.filter(sha256=sha).exists():
        return
    storage.remove(sha)


def image_choices(event) -> list[tuple[str, str]]:
    return [(str(a.pk), a.name) for a in Asset.objects.filter(owner_q(event), kind__in=["image", "svg"],
                                                              status=Asset.Status.READY).order_by("name")]


def file_owner_events(sha: str) -> tuple[set, bool]:
    """Events whose assets/fonts contain the file ``sha``, and whether it is in the shared library."""
    events = set(Asset.objects.filter(sha256=sha).values_list("event_id", flat=True))
    events |= set(FontFile.objects.filter(sha256=sha).values_list("family__event_id", flat=True))
    shared = None in events
    events.discard(None)
    return events, shared


def file_info(sha: str, name: str) -> tuple[Path, str] | None:
    """Path and MIME type of a stored file, if it belongs to an asset or font."""
    for a in Asset.objects.filter(sha256=sha):
        for v in (a.variants or {}).values():
            if v.get("file") == name:
                return storage.path(sha, name), v.get("mime", "application/octet-stream")
    if name == "font.woff2" and FontFile.objects.filter(sha256=sha).exists():
        return storage.path(sha, name), "font/woff2"
    return None


# --------------------------------------------------------------------------- themes

def themes(event) -> list[Theme]:
    return list(Theme.objects.filter(owner_q(event)).select_related("parent").order_by("event_id", "name"))


def theme_schema(event) -> dict:
    return tok.schema(fonts=font_choices(event), images=image_choices(event))


def event_theme(event) -> Theme | None:
    if not event.default_theme:
        return None
    return Theme.objects.filter(owner_q(event), key=event.default_theme).order_by("-event_id").first()


def resolved_tokens(theme: Theme | None) -> dict:
    return theme.resolved() if theme else {k: p.get("default") for k, p in tok.schema()["properties"].items()}


class Conflict(ValidationError):
    pass


@transaction.atomic
def save_theme(theme: Theme, *, actor, request=None, tokens: dict | None = None, expected_version: int | None = None,
               schema: dict | None = None) -> Theme:
    """Create or update a theme. ``expected_version`` implements optimistic locking: if somebody saved in the
    meantime, :class:`Conflict` is raised instead of silently overwriting their change."""
    creating = theme._state.adding
    current = None
    if not creating:
        current = Theme.objects.select_for_update().filter(pk=theme.pk).values_list("version", flat=True).first()
        if expected_version is not None and current != expected_version:
            raise Conflict(_("Someone else saved this theme in the meantime. Reload the page to see their changes."))
    if tokens is not None:
        errors = settings_schema.validate(schema or tok.schema(), tokens, partial=True)
        if errors:
            raise ValidationError(errors)
        theme.tokens = tokens
    if theme.parent_id and theme.parent_id == theme.pk:
        theme.parent = None
    if theme.parent and theme in theme.parent.chain():
        raise ValidationError(_("A theme cannot inherit from itself."))
    if not creating:
        theme.version = (current or theme.version) + 1
    theme.updated_by = actor
    theme.save()
    log(action="theme.created" if creating else "theme.updated", actor=actor, target=theme, event=theme.event,
        request=request, message=f"Theme {theme.name} saved (version {theme.version})")
    _notify_screens(theme)
    return theme


def delete_theme(theme: Theme, *, actor, request=None) -> None:
    if theme.children.exists():
        raise ValidationError(_("Other themes inherit from this theme."))
    log(action="theme.deleted", actor=actor, target=theme, event=theme.event, request=request,
        message=f"Theme {theme.name} deleted")
    theme.delete()


def set_event_theme(event, theme: Theme | None, *, actor, request=None) -> None:
    before = event.default_theme
    event.default_theme = theme.key if theme else ""
    event.save(update_fields=["default_theme", "updated_at"])
    log(action="theme.default_changed", actor=actor, target=event, event=event, request=request,
        changes={"default_theme": [before, event.default_theme]})
    _notify_screens(theme, event=event)


def _notify_screens(theme: Theme | None, event=None) -> None:
    """Tell paired screens to reload their configuration (design changed)."""
    try:
        from apps.screens import channel
        from apps.screens.models import Screen
    except ImportError:  # screens plugin not installed
        return
    events = [event] if event is not None else ([theme.event] if theme and theme.event_id else [])
    qs = Screen.objects.paired()
    qs = qs.filter(event__in=events) if events else qs
    for screen in qs:
        channel.send(screen, "config.changed", {})


def theme_payload(event, url_for_asset, url_for_font) -> dict:
    """Everything a renderer needs: resolved tokens, CSS variables and @font-face rules."""
    theme = event_theme(event)
    values = resolved_tokens(theme)
    images = {str(a.pk): url_for_asset(a) for a in Asset.objects.filter(owner_q(event), pk__in=[
        v for v in tok.referenced_assets(values) if _is_uuid(v)])}
    variables = tok.css_variables(values, families=font_stacks(event), urls=images)
    return {"key": theme.key if theme else "", "version": theme.version if theme else 0, "tokens": values,
            "variables": variables, "css": tok.css_block(variables),
            "fonts_css": fonts_css(event, url_for_font, only={str(values.get("font_body")),
                                                               str(values.get("font_heading"))})}


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- layouts

def _check_refs(event, data: dict) -> list[str]:
    from . import layout_format as lf

    errors = []
    assets = lf.asset_ids(data)
    if assets:
        known = {str(pk) for pk in Asset.objects.filter(owner_q(event), pk__in=[a for a in assets if _is_uuid(a)])
                 .values_list("pk", flat=True)}
        errors += [f"unknown file {a}" for a in sorted(assets - known)]
    fonts = lf.font_ids(data)
    if fonts:
        known = {str(pk) for pk in FontFamily.objects.filter(owner_q(event), pk__in=fonts).values_list("pk",
                                                                                                         flat=True)}
        errors += [f"unknown font {f}" for f in sorted(fonts - known)]
    return errors


@transaction.atomic
def may_write_code(actor, event, request=None) -> bool:
    """Code elements (HTML/CSS/JS) need ``content.code``; system actions (actor None) may."""
    if actor is None:
        return True
    if event is None:
        return bool(getattr(actor, "is_superuser", False))
    from apps.events import rbac

    return rbac.has_perm(actor, event, "content.code", request=request)


def _check_code(event, old, new, actor, request) -> None:
    from . import layout_format as lf

    if lf.code_changed(old, new) and not may_write_code(actor, event, request):
        raise ValidationError(_("Only people allowed to write code (permission content.code) may add or change "
                                "code elements."))


def _log_code(layout, old, new, actor, request) -> None:
    import hashlib

    from . import layout_format as lf

    if lf.code_changed(old, new):
        parts = lf.code_parts(new)
        log(action="layout.code_changed", actor=actor, target=layout, event=layout.event, request=request,
            message=f"Code in layout {layout.name} changed",
            changes={k: {"sha256": hashlib.sha256("\x00".join(v[:3]).encode()).hexdigest()[:16],
                         "bytes": sum(len(x) for x in v[:3]), "data": list(v[3])} for k, v in parts.items()})


def create_layout(event, *, name: str, key: str, actor, request=None, width: int = 1920, height: int = 1080,
                  starter: bool = True, data: dict | None = None):
    from . import layout_format as lf
    from .models import Layout

    if data is None:
        data = lf.starter(width, height) if starter else lf.empty(width, height)
    errors = lf.validate(data) or _check_refs(event, data)
    if errors:
        raise ValidationError(errors)
    _check_code(event, None, data, actor, request)
    layout = Layout.objects.create(event=event, name=name, key=key, data=data, updated_by=actor,
                                   is_default=event is not None and not Layout.objects.filter(event=event).exists())
    layout.versions.create(number=1, data=data, created_by=actor, note="created")
    log(action="layout.created", actor=actor, target=layout, event=event, request=request,
        message=f"Layout {name} created")
    _log_code(layout, None, data, actor, request)
    return layout


@transaction.atomic
def save_layout(layout, data: dict, *, actor, request=None, expected_version: int | None = None, note: str = ""):
    """Save the draft (every save is a version). Optimistic locking as for themes."""
    from . import layout_format as lf
    from .models import Layout

    current = Layout.objects.select_for_update().filter(pk=layout.pk).values_list("version", flat=True).first()
    if expected_version is not None and current != expected_version:
        raise Conflict(_("Someone else saved this layout in the meantime. Reload to see their version; your "
                         "changes are still in the editor."))
    errors = lf.validate(data) or _check_refs(layout.event, data)
    if errors:
        raise ValidationError(errors)
    if data == layout.data:
        return layout
    _check_code(layout.event, layout.data, data, actor, request)
    old = layout.data
    layout.data = data
    layout.version = (current or layout.version) + 1
    layout.updated_by = actor
    layout.save(update_fields=["data", "version", "updated_by", "updated_at"])
    layout.versions.create(number=layout.version, data=data, created_by=actor, note=note[:200])
    log(action="layout.saved", actor=actor, target=layout, event=layout.event, request=request,
        message=f"Layout {layout.name} saved (version {layout.version})")
    _log_code(layout, old, data, actor, request)
    return layout


@transaction.atomic
def publish_layout(layout, *, actor, request=None, version=None, at=None):
    """Publish the current draft (or ``version``) now, or schedule it for ``at``."""
    from django.utils import timezone

    if version is None:
        version = layout.versions.filter(number=layout.version).first() or layout.versions.create(
            number=layout.version, data=layout.data, created_by=actor)
    if at is not None and at > timezone.now():
        version.publish_at = at
        version.save(update_fields=["publish_at"])
        log(action="layout.publish_scheduled", actor=actor, target=layout, event=layout.event, request=request,
            message=f"Layout {layout.name} v{version.number} scheduled for {at.isoformat()}")
        return version
    version.published_at, version.publish_at = timezone.now(), None
    version.save(update_fields=["published_at", "publish_at"])
    layout.published = version
    layout.save(update_fields=["published", "updated_at"])
    log(action="layout.published", actor=actor, target=layout, event=layout.event, request=request,
        message=f"Layout {layout.name} v{version.number} published")
    _notify_screens(None, event=layout.event if layout.event_id else None)
    return version


def publish_due(now=None) -> int:
    """Publish versions whose scheduled time has come (periodic task)."""
    from django.utils import timezone

    from .models import LayoutVersion

    now = now or timezone.now()
    done = 0
    for v in LayoutVersion.objects.filter(publish_at__lte=now).select_related("layout", "created_by"):
        publish_layout(v.layout, actor=v.created_by, version=v)
        done += 1
    return done


def rollback_layout(layout, version, *, actor, request=None):
    """Make an old version the draft again (as a new version); publish separately."""
    return save_layout(layout, version.data, actor=actor, request=request, note=f"restored v{version.number}")


def set_default_layout(event, layout, *, actor, request=None) -> None:
    from .models import Layout

    Layout.objects.filter(event=event, is_default=True).exclude(pk=layout.pk).update(is_default=False)
    layout.is_default = True
    layout.save(update_fields=["is_default", "updated_at"])
    log(action="layout.default_changed", actor=actor, target=layout, event=event, request=request,
        message=f"{layout.name} is now the default layout")
    _notify_screens(None, event=event)


def delete_layout(layout, *, actor, request=None) -> None:
    log(action="layout.deleted", actor=actor, target=layout, event=layout.event, request=request,
        message=f"Layout {layout.name} deleted")
    layout.delete()


def mark_editing(layout, user) -> object | None:
    """Soft lock: remember who edits; return the other editor if someone else edited in the last 2 minutes."""
    import datetime as dt

    from django.utils import timezone

    from .models import Layout

    now = timezone.now()
    other = None
    if layout.editing_by_id and layout.editing_by_id != user.pk and layout.editing_since and \
            now - layout.editing_since < dt.timedelta(minutes=2):
        other = layout.editing_by
    Layout.objects.filter(pk=layout.pk).update(editing_by=user, editing_since=now)
    return other


def asset_entry(asset, url_for) -> dict:
    return {"id": str(asset.pk), "kind": asset.kind, "name": asset.name, "alt": asset.alt_text,
            "width": asset.width, "height": asset.height, "duration": asset.duration,
            "urls": {k: url_for(asset.sha256, v["file"]) for k, v in (asset.variants or {}).items()},
            "mimes": {k: v.get("mime", "") for k, v in (asset.variants or {}).items()}}


def bundle(event, *, url_for, font_url_for, draft_layout=None) -> dict:
    """Everything a screen needs to play offline: theme, fonts, published layouts and their assets.

    ``draft_layout`` (editor preview) replaces that layout's published data with its draft."""
    import hashlib
    import json

    from . import layout_format as lf
    from .models import Layout

    layouts = []
    for lay in Layout.objects.filter(event=event).select_related("published", "theme"):
        data = lay.data if draft_layout is not None and lay.pk == draft_layout.pk else (
            lay.published.data if lay.published_id else None)
        if data is None:
            continue
        entry = {"id": str(lay.pk), "key": lay.key, "name": lay.name, "default": lay.is_default,
                 "version": lay.published.number if lay.published_id else 0, "data": data}
        if lay.theme_id:
            entry["variables"] = tok.css_variables(lay.theme.resolved(), families=font_stacks(event))
        layouts.append(entry)
    used = set().union(*(lf.asset_ids(entry["data"]) for entry in layouts)) if layouts else set()
    assets = {str(a.pk): asset_entry(a, url_for) for a in Asset.objects.filter(
        owner_q(event), pk__in=[u for u in used if _is_uuid(u)], status=Asset.Status.READY)}
    theme = theme_payload(event, lambda a: url_for(a.sha256, a.variants[a.variant("webp", "original")]["file"]),
                          font_url_for)
    fonts_used = set().union(*(lf.font_ids(entry["data"]) for entry in layouts)) if layouts else set()
    fonts_used |= {str(theme["tokens"].get("font_body")), str(theme["tokens"].get("font_heading"))}
    payload = {
        "theme": theme, "layouts": layouts, "assets": assets,
        "fonts_css": fonts_css(event, font_url_for, only=fonts_used),
        "fonts": {str(f.pk): f.stack for f in font_families(event)},
    }
    payload["version"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return payload


def welcome_on_first_pairing(event_type: str, payload, event) -> None:
    """Webhook sink: when the first screen of an event without layouts is paired, create, publish and use a
    welcome layout, so the new screen shows something friendly right away (closes the setup wizard's loop)."""
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django.db import IntegrityError

    from apps.core import modules

    from . import layout_format as lf
    from .models import Layout

    if event_type != "screen.paired" or event is None or not modules.is_enabled("content", event):
        return
    if Layout.objects.filter(event=event).exists():
        return
    try:
        layout = create_layout(event, name="Welcome", key="welcome", actor=None, data=lf.welcome())
        publish_layout(layout, actor=None)
    except (DjangoValidationError, IntegrityError):  # pragma: no cover - a concurrent pairing created it
        return
