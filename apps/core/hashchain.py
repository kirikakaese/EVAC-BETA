# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hash chain for the tamper-evident audit log (see docs/adr/0004-audit-hash-chain.md).

Each audit row stores ``prev_hash`` (the hash of the row before it) and ``hash`` =
SHA-256(prev_hash || canonical JSON of the row's content). Changing, deleting or reordering any row
breaks every following hash, which :func:`verify` detects.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

GENESIS = "0" * 64


def canonical(payload: Mapping[str, Any]) -> bytes:
    """Deterministic JSON encoding: sorted keys, no whitespace, non-ASCII kept, ``str()`` for others."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def compute(prev_hash: str, payload: Mapping[str, Any]) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(b"\n")
    h.update(canonical(payload))
    return h.hexdigest()


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    first_bad_id: Any = None
    reason: str = ""


def verify(rows: Iterable[tuple[Any, str, str, Mapping[str, Any]]]) -> VerifyResult:
    """Verify ``(id, prev_hash, hash, payload)`` rows in chain order."""
    expected_prev = GENESIS
    n = 0
    for row_id, prev_hash, row_hash, payload in rows:
        n += 1
        if prev_hash != expected_prev:
            return VerifyResult(False, n, row_id,
                                "prev_hash does not match the previous row (row removed or reordered)")
        if compute(prev_hash, payload) != row_hash:
            return VerifyResult(False, n, row_id, "content does not match its hash (row modified)")
        expected_prev = row_hash
    return VerifyResult(True, n)
