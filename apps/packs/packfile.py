# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ``.evacpack`` file format (ADR-0024).

A zip archive with exactly these entries:

* ``manifest.json``: ``{"format": "evacpack", "version": 1, "name", "description", "created", "generator",
  "modules": [...], "sections": {section: [items]}, "files": {sha256: {"name", "size"}}}``
* ``files/<sha256>``: every file the items refer to (by its hash)
* ``signature.json`` (optional): ``{"algorithm": "Ed25519", "public_key", "signer", "signature"}``, the signature
  over the exact bytes of ``manifest.json`` (base64). The manifest lists the hash of every file, so the signature
  covers the whole pack.

Reading checks the structure, the sizes (the zip headers are not trusted: entries are read with a limit), every
file hash and the signature. Anything unexpected is refused.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

FORMAT = "evacpack"
VERSION = 1
MANIFEST = "manifest.json"
SIGNATURE = "signature.json"
FILE_RE = re.compile(r"^files/([0-9a-f]{64})$")
MAX_MANIFEST = 20 * 1024 * 1024
MAX_FILES = 2000
CHUNK = 1024 * 1024


class PackError(ValueError):
    pass


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def fingerprint(public_key: str) -> str:
    """A short, readable form of a public key: ``AB12 CD34 …`` (first 16 bytes of its SHA-256)."""
    try:
        raw = base64.b64decode(public_key, validate=True)
    except ValueError:
        return "?"
    digest = hashlib.sha256(raw).hexdigest()[:32].upper()
    return " ".join(digest[i:i + 4] for i in range(0, 32, 4))


# ------------------------------------------------------------------ writing
@dataclass
class FileSet:
    """Files of a pack being written, keyed by hash (the same file is packed once)."""

    files: dict[str, tuple[str, Path | bytes]] = field(default_factory=dict)

    def add(self, src: Path | bytes, name: str) -> str:
        data_hash = hashlib.sha256()
        if isinstance(src, bytes):
            data_hash.update(src)
        else:
            with open(src, "rb") as fh:
                for chunk in iter(lambda: fh.read(CHUNK), b""):
                    data_hash.update(chunk)
        sha = data_hash.hexdigest()
        self.files.setdefault(sha, (Path(name).name[:200], src))
        return sha

    def size(self, sha: str) -> int:
        src = self.files[sha][1]
        return len(src) if isinstance(src, bytes) else src.stat().st_size


def write(out: IO[bytes], *, name: str, description: str, sections: dict[str, list[dict[str, Any]]],
          files: FileSet, modules: list[str], generator: str, signer: tuple[Ed25519PrivateKey, str] | None,
          created: dt.datetime | None = None) -> dict[str, Any]:
    """Write a pack to ``out``; returns the manifest."""
    manifest = {
        "format": FORMAT, "version": VERSION, "name": name, "description": description,
        "created": (created or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds"), "generator": generator,
        "modules": sorted(set(modules)), "sections": sections,
        "files": {sha: {"name": n, "size": files.size(sha)} for sha, (n, _src) in sorted(files.files.items())},
    }
    data = json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True).encode()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, data)
        if signer:
            key, signer_name = signer
            pub = key.public_key().public_bytes_raw()
            zf.writestr(SIGNATURE, json.dumps({"algorithm": "Ed25519", "public_key": b64(pub), "signer": signer_name,
                                               "signature": b64(key.sign(data))}, indent=1))
        for sha, (_n, src) in sorted(files.files.items()):
            if isinstance(src, bytes):
                zf.writestr(f"files/{sha}", src, compress_type=zipfile.ZIP_STORED)
            else:
                zf.write(src, f"files/{sha}", compress_type=zipfile.ZIP_DEFLATED)
    return manifest


# ------------------------------------------------------------------ reading
@dataclass
class Pack:
    manifest: dict[str, Any]
    signed: bool = False
    public_key: str = ""
    signer: str = ""

    @property
    def sections(self) -> dict[str, list[dict[str, Any]]]:
        return self.manifest.get("sections") or {}


def _read(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> Iterator[bytes]:
    total = 0
    with zf.open(info) as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            total += len(chunk)
            if total > limit:
                raise PackError(f"{info.filename} is larger than allowed.")
            yield chunk


def _read_all(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    return b"".join(_read(zf, info, limit))


def _entries(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    out: dict[str, zipfile.ZipInfo] = {}
    for info in zf.infolist():
        name = info.filename
        if name in out:
            raise PackError(f"The pack contains {name} twice.")
        if name not in (MANIFEST, SIGNATURE) and not FILE_RE.match(name):
            raise PackError(f"Unexpected entry in the pack: {name[:80]}")
        out[name] = info
    if len(out) > MAX_FILES + 2:
        raise PackError("The pack contains too many files.")
    return out


def _check_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise PackError("This is not an EVAC pack (manifest.json missing or wrong format).")
    if manifest.get("version") != VERSION:
        raise PackError(f"Pack format version {manifest.get('version')} is not supported by this EVAC version.")
    if not isinstance(manifest.get("sections"), dict) or not isinstance(manifest.get("files"), dict):
        raise PackError("The pack manifest is incomplete.")
    for key, items in manifest["sections"].items():
        if not isinstance(items, list) or not all(isinstance(i, dict) and "id" in i for i in items):
            raise PackError(f"The pack section {str(key)[:40]} is malformed.")
    return manifest


def read(src: IO[bytes] | Path | bytes, *, max_bytes: int) -> Pack:
    """Open and verify a pack (structure, sizes, hashes, signature). Raises :class:`PackError`."""
    if isinstance(src, bytes):
        src = io.BytesIO(src)
    try:
        zf = zipfile.ZipFile(src)
    except (zipfile.BadZipFile, OSError):
        raise PackError("This is not an EVAC pack (not a zip file).") from None
    with zf:
        entries = _entries(zf)
        if MANIFEST not in entries:
            raise PackError("This is not an EVAC pack (manifest.json missing).")
        data = _read_all(zf, entries[MANIFEST], MAX_MANIFEST)
        try:
            manifest = _check_manifest(json.loads(data))
        except ValueError as exc:
            if isinstance(exc, PackError):
                raise
            raise PackError("The pack manifest is not valid JSON.") from None
        pack = Pack(manifest=manifest)
        if SIGNATURE in entries:
            try:
                sig = json.loads(_read_all(zf, entries[SIGNATURE], 64 * 1024))
                if sig.get("algorithm") != "Ed25519":
                    raise PackError("Unknown signature algorithm.")
                public = Ed25519PublicKey.from_public_bytes(base64.b64decode(sig["public_key"], validate=True))
                public.verify(base64.b64decode(sig["signature"], validate=True), data)
            except InvalidSignature:
                raise PackError("The signature does not match: the pack was changed after it was signed.") from None
            except PackError:
                raise
            except (ValueError, KeyError, TypeError, AttributeError):
                raise PackError("The signature file is malformed.") from None
            pack.signed, pack.public_key, pack.signer = True, str(sig["public_key"]), str(sig.get("signer", ""))[:200]
        listed = manifest["files"]
        present = {m.group(1) for name in entries if (m := FILE_RE.match(name))}
        if set(listed) != present:
            raise PackError("The files in the pack do not match its manifest.")
        total = 0
        for sha in sorted(present):
            h = hashlib.sha256()
            for chunk in _read(zf, entries[f"files/{sha}"], max_bytes):
                h.update(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise PackError("The pack is larger than allowed.")
            if h.hexdigest() != sha:
                raise PackError("A file in the pack is damaged (its hash does not match).")
    return pack


def extract(src: Path, sha: str, dst: Path, *, max_bytes: int) -> Path:
    """Copy one packed file to ``dst`` (checking its hash again)."""
    with zipfile.ZipFile(src) as zf:
        try:
            info = zf.getinfo(f"files/{sha}")
        except KeyError:
            raise PackError("A file is missing from the pack.") from None
        h = hashlib.sha256()
        with open(dst, "wb") as out:
            for chunk in _read(zf, info, max_bytes):
                h.update(chunk)
                out.write(chunk)
    if h.hexdigest() != sha:
        dst.unlink(missing_ok=True)
        raise PackError("A file in the pack is damaged (its hash does not match).")
    return dst
