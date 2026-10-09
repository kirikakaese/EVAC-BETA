# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP calls of the channel adapters. Errors never contain the URL (Telegram puts the bot token into it)."""
from __future__ import annotations

from typing import Any

import requests

TIMEOUT = 10
USER_AGENT = "EVAC-Announcements/1"


class Rejected(Exception):
    """The service refused the message (4xx): retrying will not help; the delivery is marked failed."""


class Temporary(Exception):
    """Network trouble, 429 or 5xx: the outbox retries with backoff."""


def call(method: str, url: str, *, json: Any = None, headers: dict[str, str] | None = None,
         timeout: float = TIMEOUT) -> Any:
    try:
        r = requests.request(method, url, json=json, timeout=timeout,
                             headers={"User-Agent": USER_AGENT, **(headers or {})})
    except requests.RequestException as exc:
        raise Temporary(f"{type(exc).__name__}: no answer from the service") from None
    if r.status_code == 429 or r.status_code >= 500:
        raise Temporary(f"HTTP {r.status_code}")
    if r.status_code >= 400:
        raise Rejected(f"HTTP {r.status_code}: {_reason(r)}")
    try:
        return r.json()
    except ValueError:
        return {}


def _reason(r) -> str:
    try:
        data = r.json()
    except ValueError:
        return (r.text or "")[:200]
    if isinstance(data, dict):
        for key in ("error", "description", "message", "errcode"):
            if data.get(key):
                return str(data[key])[:200]
    return str(data)[:200]
