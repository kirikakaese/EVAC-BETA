# SPDX-License-Identifier: AGPL-3.0-or-later
"""DNS rebinding: the connection goes to the address that was checked, not to a second DNS answer."""
import http.server
import socket
import threading

import pytest

from apps.core import safefetch

REAL = socket.getaddrinfo


@pytest.fixture
def server(monkeypatch):
    for var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.delenv(var, raising=False)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = f"host={self.headers['Host']}".encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def rebinding_dns(monkeypatch):
    """feed.example: "public" (here 127.0.0.1, the test server) for the first lookup, an unroutable address after."""
    calls = []

    def fake(host, *args, **kwargs):
        if host != "feed.example":
            return REAL(host, *args, **kwargs)
        calls.append(host)
        addr = "127.0.0.1" if len(calls) == 1 else "10.255.255.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, args[0] if args else 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    monkeypatch.setattr(safefetch, "_blocked", lambda ip: str(ip) != "127.0.0.1")  # the first answer counts as public
    return calls


def test_connection_goes_to_the_checked_address(server, monkeypatch):
    calls = rebinding_dns(monkeypatch)
    got = safefetch.get(f"http://feed.example:{server}/data")
    assert got.status == 200 and got.body == f"host=feed.example:{server}".encode()
    assert calls == ["feed.example"]  # resolved once; the rebinding answer was never used


def test_a_private_first_answer_is_refused(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                                                                        ("10.0.0.5", 80))])
    with pytest.raises(safefetch.FetchError, match="private network"):
        safefetch.get("http://feed.example/")


def test_pins_are_per_thread_and_released(server, monkeypatch):
    rebinding_dns(monkeypatch)
    safefetch.get(f"http://feed.example:{server}/")
    assert getattr(safefetch._pins, "hosts", {}) == {}
    seen = []
    t = threading.Thread(target=lambda: seen.append(getattr(safefetch._pins, "hosts", {})))
    with safefetch._pinned("feed.example", "192.0.2.1"):
        t.start()
        t.join()
        assert safefetch._pins.hosts == {"feed.example": "192.0.2.1"}
    assert seen == [{}]
