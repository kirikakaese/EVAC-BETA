# SPDX-License-Identifier: AGPL-3.0-or-later
"""The player may fetch signed alarm state from the configured fallback origins (ADR-0034): they are in the
page's connect-src, and nothing else gets in."""
from django.test import Client

from apps.core import settings_store


def test_fallback_origins_in_connect_src(db, event):
    csp = Client().get("/player/")["Content-Security-Policy"]
    connect = next(d for d in csp.split("; ") if d.startswith("connect-src"))
    assert connect == "connect-src 'self' ws: wss:"
    settings_store.save("evacuation", "event", str(event.pk), {"fallback_origins": [
        "https://bridge-a.venue.lan:8443/", "http://10.0.0.5:8088"]}, event=event)
    # whatever is stored, only plain origins get into the policy
    from apps.core.models import SettingValue

    SettingValue.objects.create(namespace="evacuation", level="instance", scope_id="",
                                values={"fallback_origins": ["https://evil.example; script-src *", "javascript:x"]})
    csp = Client().get("/player/")["Content-Security-Policy"]
    connect = next(d for d in csp.split("; ") if d.startswith("connect-src"))
    assert connect == "connect-src 'self' ws: wss: http://10.0.0.5:8088 https://bridge-a.venue.lan:8443"
    assert "evil" not in csp and "javascript" not in csp
