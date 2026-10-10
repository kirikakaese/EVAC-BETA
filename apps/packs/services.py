# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exporting and importing ``.evacpack`` files (ADR-0024): signing key, trusted keys, staged imports."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import IO, Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

import evac
from apps.core import crypto, safefetch, settings_store
from apps.core.audit import log

from . import engine, gallery, packfile
from .models import PackImport, SigningKey, TrustedKey

KEEP_DAYS = 7


def config() -> dict[str, Any]:
    return settings_store.get("packs")


def max_bytes() -> int:
    return int(config().get("max_size_mb") or 200) * 1024 * 1024


def storage_dir() -> Path:
    path = Path(settings.MEDIA_ROOT) / "packs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def staged_path(pi: PackImport) -> Path:
    return storage_dir() / f"{pi.pk}.evacpack"


# ------------------------------------------------------------------ keys
def signing_key() -> SigningKey:
    """The instance key pair (created on first use)."""
    row = SigningKey.objects.first()
    if row is None:
        with transaction.atomic():
            row = SigningKey.objects.select_for_update().first()
            if row is None:
                key = Ed25519PrivateKey.generate()
                pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()).decode()
                row = SigningKey.objects.create(private_key_encrypted=crypto.encrypt(pem),
                                                public_key=packfile.b64(key.public_key().public_bytes_raw()))
    return row


def _private_key() -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(crypto.decrypt(signing_key().private_key_encrypted).encode(), None)
    assert isinstance(key, Ed25519PrivateKey)
    return key


def own_public_key() -> str:
    return signing_key().public_key


def valid_public_key(value: str) -> str:
    value = (value or "").strip()
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        raw = b""
    if len(raw) != 32:
        raise ValidationError(_("This is not an Ed25519 public key (44 characters of base64)."))
    return value


def trust_key(public_key: str, name: str, *, actor, request=None) -> TrustedKey:
    public_key = valid_public_key(public_key)
    name = (name or "").strip()[:200] or packfile.fingerprint(public_key)
    row, created = TrustedKey.objects.update_or_create(public_key=public_key,
                                                       defaults={"name": name, "added_by": actor})
    log(action="packs.key_trusted", actor=actor, target=row, request=request,
        message=f"Pack key {name} trusted ({packfile.fingerprint(public_key)})",
        changes={"public_key": public_key, "created": created})
    return row


def untrust_key(row: TrustedKey, *, actor, request=None) -> None:
    log(action="packs.key_untrusted", actor=actor, target=row, request=request,
        message=f"Pack key {row.name} no longer trusted ({packfile.fingerprint(row.public_key)})",
        changes={"public_key": row.public_key})
    row.delete()


def trust_of(pack: packfile.Pack) -> str:
    if not pack.signed:
        return PackImport.Trust.UNSIGNED
    if pack.public_key == own_public_key() or TrustedKey.objects.filter(public_key=pack.public_key).exists():
        return PackImport.Trust.TRUSTED
    return PackImport.Trust.UNTRUSTED


# ------------------------------------------------------------------ export
def export(event, selection: Mapping[str, set[str]], *, name: str, description: str = "", actor, request=None,
           sign: bool = True, out: IO[bytes] | None = None) -> IO[bytes]:
    """Write a pack of the selected objects (and what they need) to ``out`` (a temporary file by default)."""
    sections, files, mods = engine.dump(event, selection)
    if not sections:
        raise ValidationError(_("Choose at least one thing to export."))
    out = out or tempfile.TemporaryFile()
    signer = (_private_key(), str(config().get("signer_name") or "EVAC")) if sign else None
    manifest = packfile.write(out, name=name.strip()[:200] or event.name, description=description.strip()[:2000],
                              sections=sections, files=files, modules=mods,
                              generator=f"EVAC {evac.__version__}", signer=signer)
    out.seek(0)
    log(action="packs.exported", actor=actor, target=event, event=event, request=request,
        message=f"Pack {manifest['name']} exported",
        changes={"sections": {k: len(v) for k, v in sections.items()}, "files": len(files.files), "signed": sign})
    return out


# ------------------------------------------------------------------ staging
def _inspect(pi: PackImport, path: Path) -> PackImport:
    """Verify the staged file and record what it contains."""
    try:
        pack = packfile.read(path, max_bytes=max_bytes())
    except packfile.PackError as exc:
        path.unlink(missing_ok=True)
        pi.status, pi.error = PackImport.Status.FAILED, str(exc)
        pi.save()
        return pi
    m = pack.manifest
    pi.name = str(m.get("name") or "")[:200]
    pi.description = str(m.get("description") or "")[:2000]
    pi.contents = {k: [{"id": str(i.get("id"))[:64], "name": str(i.get("name") or i.get("key") or "")[:200]}
                       for i in items] for k, items in pack.sections.items()}
    if pi.source == PackImport.Source.GALLERY:
        pi.trust = PackImport.Trust.BUILTIN
    else:
        pi.trust, pi.signer, pi.public_key = trust_of(pack), pack.signer, pack.public_key
    pi.status, pi.error = PackImport.Status.READY, ""
    pi.save()
    return pi


def _store_upload(pi: PackImport, upload) -> None:
    limit = max_bytes()
    h, size = hashlib.sha256(), 0
    path = staged_path(pi)
    with open(path, "wb") as out:
        for chunk in (upload.chunks() if hasattr(upload, "chunks") else iter(lambda: upload.read(1 << 20), b"")):
            size += len(chunk)
            if size > limit:
                out.close()
                path.unlink(missing_ok=True)
                raise ValidationError(_("Packs may be at most %(mb)s MB.") % {"mb": limit // 1024 // 1024})
            h.update(chunk)
            out.write(chunk)
    pi.sha256, pi.size = h.hexdigest(), size


def stage_upload(event, upload, *, actor, request=None) -> PackImport:
    pi = PackImport(event=event, source=PackImport.Source.UPLOAD, file_name=Path(upload.name or "").name[:255],
                    created_by=actor)
    _store_upload(pi, upload)
    pi.save()
    _inspect(pi, staged_path(pi))
    log(action="packs.staged", actor=actor, target=event, event=event, request=request,
        message=f"Pack {pi.file_name} uploaded for review",
        changes={"sha256": pi.sha256, "status": pi.status, "trust": pi.trust})
    return pi


def stage_url(event, url: str, *, actor, request=None) -> PackImport:
    cfg = config()
    if not cfg.get("allow_url_import", True):
        raise ValidationError(_("Importing packs from a URL is switched off on this server."))
    try:
        safefetch.check_url(url, allow_private=bool(cfg.get("allow_private_networks")))
    except safefetch.FetchError as exc:
        raise ValidationError(str(exc)) from None
    pi = PackImport.objects.create(event=event, source=PackImport.Source.URL, url=url[:1000],
                                   file_name=Path(url.split("?", 1)[0]).name[:255], created_by=actor)
    log(action="packs.staged", actor=actor, target=event, event=event, request=request,
        message=f"Pack download from {url[:200]} requested", changes={"url": url[:1000]})
    from .tasks import download

    transaction.on_commit(lambda: download.delay(str(pi.pk)))
    return pi


def download(pi: PackImport) -> PackImport:
    """Fetch a URL import (Celery task; never inside a request)."""
    if pi.status != PackImport.Status.FETCHING:
        return pi
    cfg = config()
    try:
        got = safefetch.get(pi.url, allow_private=bool(cfg.get("allow_private_networks")), max_bytes=max_bytes())
    except safefetch.FetchError as exc:
        pi.status, pi.error = PackImport.Status.FAILED, str(exc)
        pi.save()
        return pi
    staged_path(pi).write_bytes(got.body)
    pi.sha256, pi.size = hashlib.sha256(got.body).hexdigest(), len(got.body)
    pi.save()
    return _inspect(pi, staged_path(pi))


def stage_gallery(event, key: str, *, actor, request=None) -> PackImport:
    entry = gallery.get(key)
    if entry is None:
        raise ValidationError(_("Unknown gallery pack."))
    pi = PackImport(event=event, source=PackImport.Source.GALLERY, gallery_key=key, file_name=f"{key}.evacpack",
                    created_by=actor)
    data = gallery.build(entry)
    staged_path(pi).write_bytes(data)
    pi.sha256, pi.size = hashlib.sha256(data).hexdigest(), len(data)
    pi.save()
    return _inspect(pi, staged_path(pi))


def needs_confirmation(pi: PackImport) -> bool:
    return pi.trust in (PackImport.Trust.UNTRUSTED, PackImport.Trust.UNSIGNED)


def blocked_reason(pi: PackImport) -> str:
    """Why this staged pack cannot be imported right now ("" = it can)."""
    if pi.status != PackImport.Status.READY:
        return _("This pack is not ready to import.")
    if needs_confirmation(pi) and config().get("require_trusted"):
        return _("This server only imports packs signed by a trusted key.")
    return ""


def apply(pi: PackImport, *, actor, request=None, confirmed: bool = False) -> dict[str, Any]:
    """Import a staged pack into its event (all or nothing)."""
    reason = blocked_reason(pi)
    if reason:
        raise ValidationError(reason)
    if needs_confirmation(pi) and not confirmed:
        raise ValidationError(_("Confirm that you trust where this pack comes from."))
    path = staged_path(pi)
    limit = max_bytes()
    try:
        pack = packfile.read(path, max_bytes=limit)
    except (packfile.PackError, OSError) as exc:
        raise ValidationError(str(exc)) from None
    missing = engine.missing_modules(pi.event, pack)
    if missing:
        raise ValidationError(_("This pack needs modules that are off in this event: %(m)s.")
                              % {"m": ", ".join(missing)})
    try:
        with transaction.atomic():
            result = engine.load(pi.event, pack, actor=actor, request=request, path=path, max_bytes=limit)
            pi.status, pi.result, pi.imported_at = PackImport.Status.IMPORTED, result, timezone.now()
            pi.save()
            log(action="packs.imported", actor=actor, target=pi.event, event=pi.event, request=request,
                message=f"Pack {pi.name or pi.file_name} imported",
                changes={"source": pi.source, "url": pi.url, "gallery": pi.gallery_key, "sha256": pi.sha256,
                         "trust": pi.trust, "signer": pi.signer,
                         "key": packfile.fingerprint(pi.public_key) if pi.public_key else "",
                         "created": {k: len(v) for k, v in result["created"].items()},
                         "warnings": len(result["warnings"])})
    except packfile.PackError as exc:
        raise ValidationError(str(exc)) from None
    path.unlink(missing_ok=True)
    return result


def discard(pi: PackImport, *, actor, request=None) -> None:
    staged_path(pi).unlink(missing_ok=True)
    pi.delete()


def cleanup(now: dt.datetime | None = None) -> int:
    """Remove staged files that were imported, failed or left for ``KEEP_DAYS``; the rows stay as history."""
    now = now or timezone.now()
    removed = 0
    for pi in PackImport.objects.exclude(status=PackImport.Status.FETCHING).filter(
            created_at__lt=now - dt.timedelta(days=KEEP_DAYS)) | PackImport.objects.filter(
            status__in=[PackImport.Status.IMPORTED, PackImport.Status.FAILED]):
        path = staged_path(pi)
        if path.exists():
            path.unlink()
            removed += 1
    PackImport.objects.filter(status=PackImport.Status.READY,
                              created_at__lt=now - dt.timedelta(days=KEEP_DAYS)).delete()
    PackImport.objects.filter(status=PackImport.Status.FETCHING,
                              created_at__lt=now - dt.timedelta(days=1)).update(
        status=PackImport.Status.FAILED, error="The download did not finish.")
    return removed

