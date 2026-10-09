# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetching feed URLs safely (ADR-0023): event staff enter these URLs, so the server must not become a way into
the internal network. Only http(s); every address the host name resolves to must be public unless the instance
allows private networks (venue LAN sensors); redirects are followed by hand and checked again; at most
``MAX_BYTES`` and ``TIMEOUT`` seconds."""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 10
MAX_REDIRECTS = 3
USER_AGENT = "EVAC-Feeds/1"


class FetchError(Exception):
    pass


@dataclass
class Fetched:
    status: int
    body: bytes
    content_type: str
    etag: str


def _blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
            or ip.is_unspecified)


def check_url(url: str, *, allow_private: bool = False) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http and https URLs are allowed.")
    if parts.username or parts.password:
        raise FetchError("Put credentials into the authorization header, not into the URL.")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise FetchError(f"Unknown host {parts.hostname}.") from None
    for info in infos:
        if _blocked(ipaddress.ip_address(info[4][0])):
            raise FetchError(f"{parts.hostname} is in a private network; an administrator can allow private "
                             "networks for feeds.")


def get(url: str, *, headers: dict[str, str] | None = None, etag: str = "", allow_private: bool = False) -> Fetched:
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    if etag:
        headers["If-None-Match"] = etag
    for _hop in range(MAX_REDIRECTS + 1):
        check_url(url, allow_private=allow_private)
        try:
            r = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=False)
        except requests.RequestException as exc:
            raise FetchError(f"{type(exc).__name__}: the source did not answer.") from None
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            url = urljoin(url, r.headers["Location"])
            r.close()
            continue
        if r.status_code == 304:
            return Fetched(304, b"", "", etag)
        if r.status_code >= 400:
            r.close()
            raise FetchError(f"The source answered HTTP {r.status_code}.")
        body = bytearray()
        for chunk in r.iter_content(65536):
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                r.close()
                raise FetchError(f"More than {MAX_BYTES // 1024 // 1024} MB.")
        return Fetched(r.status_code, bytes(body), r.headers.get("Content-Type", ""), r.headers.get("ETag", ""))
    raise FetchError("Too many redirects.")
