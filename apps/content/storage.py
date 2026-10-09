# SPDX-License-Identifier: AGPL-3.0-or-later
"""Content-addressed file storage below ``MEDIA_ROOT/content/<sha[:2]>/<sha>/<variant file>``."""
from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
from pathlib import Path

from django.conf import settings

SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,60}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


def root() -> Path:
    return Path(settings.MEDIA_ROOT) / "content"


def directory(sha: str) -> Path:
    if not SHA.match(sha):
        raise ValueError("bad hash")
    return root() / sha[:2] / sha


def path(sha: str, name: str) -> Path:
    if not SAFE_NAME.match(name):
        raise ValueError("bad file name")
    return directory(sha) / name


def spool(fileobj, max_bytes: int) -> tuple[Path, str, int]:
    """Copy an upload to a temporary file while hashing it. Raises ``ValueError`` when it is too large."""
    h = hashlib.sha256()
    size = 0
    tmp = tempfile.NamedTemporaryFile(prefix="evac-upload-", delete=False)
    try:
        for chunk in (fileobj.chunks() if hasattr(fileobj, "chunks") else iter(lambda: fileobj.read(65536), b"")):
            size += len(chunk)
            if size > max_bytes:
                raise ValueError("too large")
            h.update(chunk)
            tmp.write(chunk)
    except Exception:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        raise
    tmp.close()
    return Path(tmp.name), h.hexdigest(), size


def store(sha: str, name: str, src: Path, *, move: bool = False) -> Path:
    dst = path(sha, name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(src), dst)
    else:
        shutil.copyfile(src, dst)
    return dst


def write_bytes(sha: str, name: str, data: bytes) -> Path:
    dst = path(sha, name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return dst


def remove(sha: str) -> None:
    shutil.rmtree(directory(sha), ignore_errors=True)
