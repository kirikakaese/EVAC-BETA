# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fetching URLs that people entered, safely (ADR-0023; used by data feeds and pack import): the server must not
become a way into the internal network. Only http(s); every address the host name resolves to must be public
unless the instance allows private networks (venue LAN sensors); redirects are followed by hand and checked again;
at most ``max_bytes`` (default ``MAX_BYTES``) and ``TIMEOUT`` seconds.

The connection goes to exactly the address that was checked (the host name is resolved once): otherwise a host that
answers DNS with a public address for the check and a private one for the connection (DNS rebinding) would reach
the internal network. Only the TCP connection is pinned, so the Host header, SNI and the certificate check still use
the host name. Behind an egress proxy (``HTTPS_PROXY``) the proxy resolves the name itself."""
from __future__ import annotations

import ipaddress
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests
import urllib3.util.connection

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 10
MAX_REDIRECTS = 3
USER_AGENT = "EVAC/1"


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


def _parts(url: str):  # noqa: ANN202 - urllib's SplitResult
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http and https URLs are allowed.")
    if parts.username or parts.password:
        raise FetchError("Put credentials into the authorization header, not into the URL.")
    return parts


def resolve(url: str) -> str:
    """The address to connect to for ``url``: every address the host resolves to must be public; the first one is
    used. ``FetchError`` otherwise."""
    parts = _parts(url)
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                   type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise FetchError(f"Unknown host {parts.hostname}.") from None
    if not infos:
        raise FetchError(f"Unknown host {parts.hostname}.")
    for info in infos:
        if _blocked(ipaddress.ip_address(info[4][0])):
            raise FetchError(f"{parts.hostname} is in a private network; an administrator can allow private "
                             "networks for feeds.")
    return str(infos[0][4][0])


def check_url(url: str, *, allow_private: bool = False) -> None:
    _parts(url)
    if not allow_private:
        resolve(url)


_pins = threading.local()
_create_connection = urllib3.util.connection.create_connection


def _pinned_create_connection(address, *args, **kwargs):  # type: ignore[no-untyped-def]
    """urllib3's connect, but to the checked address for a host pinned in this thread."""
    host, port = address
    pinned = getattr(_pins, "hosts", {}).get(host)
    return _create_connection((pinned or host, port), *args, **kwargs)


urllib3.util.connection.create_connection = _pinned_create_connection


@contextmanager
def _pinned(host: str, address: str) -> Iterator[None]:
    before = getattr(_pins, "hosts", {})
    _pins.hosts = {**before, host: address}
    try:
        yield
    finally:
        _pins.hosts = before


def _request(method: str, url: str, *, allow_private: bool, **kwargs) -> requests.Response:  # type: ignore[no-untyped-def]
    """One request without following redirects, connected to the checked address unless private networks are
    allowed."""
    parts = _parts(url)
    send = requests.get if method == "GET" else requests.post
    if allow_private:
        return send(url, allow_redirects=False, **kwargs)
    address = resolve(url)
    with _pinned(str(parts.hostname), address):
        return send(url, allow_redirects=False, **kwargs)


def post(url: str, *, json: object = None, headers: dict[str, str] | None = None, allow_private: bool = False,
         timeout: float = TIMEOUT) -> requests.Response:
    """A POST to a URL people entered (pretix check-ins), pinned like ``get``; redirects are not followed."""
    try:
        return _request("POST", url, allow_private=allow_private, json=json, timeout=timeout,
                        headers={"User-Agent": USER_AGENT, **(headers or {})})
    except requests.RequestException as exc:
        raise FetchError(f"{type(exc).__name__}: the service did not answer.") from None


def get(url: str, *, headers: dict[str, str] | None = None, etag: str = "", allow_private: bool = False,
        max_bytes: int = MAX_BYTES) -> Fetched:
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    if etag:
        headers["If-None-Match"] = etag
    for _hop in range(MAX_REDIRECTS + 1):
        try:
            r = _request("GET", url, allow_private=allow_private, headers=headers, timeout=TIMEOUT, stream=True)
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
            if len(body) > max_bytes:
                r.close()
                raise FetchError(f"More than {max_bytes // 1024 // 1024} MB.")
        return Fetched(r.status_code, bytes(body), r.headers.get("Content-Type", ""), r.headers.get("ETag", ""))
    raise FetchError("Too many redirects.")
