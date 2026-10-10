# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP client for the DIAL REST API (``/api/v1/``, ``Authorization: Bearer dial_…``).

Errors never contain the token. ``Rejected`` (4xx) means retrying will not help; ``Temporary`` (network trouble,
429, 5xx) lets the outbox retry with backoff.
"""
from __future__ import annotations

from typing import Any

import requests

TIMEOUT = 10
USER_AGENT = "EVAC-DIAL/1"
MAX_DOWNLOAD = 50 * 1024 * 1024


class DialError(Exception):
    pass


class Rejected(DialError):
    """DIAL refused the request (4xx)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Temporary(DialError):
    """No answer, 429 or 5xx: try again later."""


class Client:
    def __init__(self, base_url: str, token: str, event: str, *, verify_tls: bool = True, timeout: float = TIMEOUT):
        self.base = (base_url or "").strip().rstrip("/")
        self.token = token
        self.event = event
        self.verify = verify_tls
        self.timeout = timeout

    @classmethod
    def for_config(cls, config: Any) -> Client:
        s = config.settings or {}
        return cls(s.get("base_url", ""), config.secret("token"), s.get("event", ""),
                   verify_tls=bool(s.get("verify_tls", True)), timeout=float(s.get("timeout_seconds") or TIMEOUT))

    def url(self, path: str) -> str:
        return f"{self.base}/api/v1/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        h = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None,
                accept: tuple[int, ...] = ()) -> tuple[int, Any]:
        """Call ``/api/v1/<path>``; returns ``(status, json)``. Statuses in ``accept`` are returned, not raised."""
        if not self.base:
            raise Rejected("No DIAL URL configured.", 0)
        try:
            r = requests.request(method, self.url(path), params=params, json=json, headers=self._headers(),
                                 timeout=self.timeout, verify=self.verify, allow_redirects=False)
        except requests.RequestException as exc:
            raise Temporary(f"{type(exc).__name__}: DIAL did not answer") from None
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code in accept:
            return r.status_code, data
        if r.status_code == 429 or r.status_code >= 500:
            raise Temporary(f"HTTP {r.status_code}{_reason(data)}")
        if r.status_code >= 300:
            raise Rejected(f"HTTP {r.status_code}{_reason(data)}", r.status_code)
        return r.status_code, data

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params=params or None)[1]

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("POST", path, json=body)[1]

    def results(self, path: str, *, limit: int = 500, **params: Any) -> list[Any]:
        """All items of a list endpoint (paginated ``{count, next, results}`` or a plain list), up to ``limit``."""
        out: list[Any] = []
        offset = 0
        while len(out) < limit:
            data = self.get(path, limit=min(200, limit - len(out)), offset=offset, **params)
            if isinstance(data, list):
                return (out + data)[:limit]
            page = (data or {}).get("results") or []
            out += page
            if not page or not (data or {}).get("next"):
                break
            offset += len(page)
        return out[:limit]

    def download(self, url: str, *, max_bytes: int = MAX_DOWNLOAD) -> bytes:
        """Fetch a file DIAL links to (same host as the API only, so the token never leaves for another server)."""
        if not url.startswith(self.base + "/"):
            raise Rejected("The file is not on the DIAL server.", 0)
        try:
            with requests.get(url, headers=self._headers(), timeout=self.timeout, verify=self.verify, stream=True,
                              allow_redirects=False) as r:
                if r.status_code == 429 or r.status_code >= 500:
                    raise Temporary(f"HTTP {r.status_code}")
                if r.status_code >= 300:
                    raise Rejected(f"HTTP {r.status_code}", r.status_code)
                chunks, size = [], 0
                for chunk in r.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise Rejected("The file is too large.", 0)
                    chunks.append(chunk)
                return b"".join(chunks)
        except requests.RequestException as exc:
            raise Temporary(f"{type(exc).__name__}: DIAL did not answer") from None


def _reason(data: Any) -> str:
    if isinstance(data, dict):
        for key in ("detail", "error", "message"):
            if data.get(key):
                return f": {str(data[key])[:200]}"
    return ""
