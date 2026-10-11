# SPDX-License-Identifier: AGPL-3.0-or-later
"""Template gallery (roadmap 9.3, ADR-0046)."""
import json
import re

import pytest

from apps.content import gallery, layout_format, services
from apps.content.models import Layout
from apps.core import modules
from apps.core.a11y import audit_url
from apps.core.plugins import LayoutTemplateSpec
from apps.core.registry import registry
from conftest import login_2fa

pytestmark = pytest.mark.django_db


def test_every_registered_template_is_a_valid_layout(event, admin):
    specs = registry.ensure_loaded().layout_templates
    assert {"welcome", "info-board", "portrait-info", "countdown", "sponsors", "wayfinding",
            "program-stage", "program-day"} <= set(specs)
    for spec in specs.values():
        data = spec.data()
        assert layout_format.validate(data) == [], spec.key
        # creatable as a layout of an event (references, code permission)
        services.create_layout(event, name=spec.name, key=spec.key, actor=admin, data=data)
    assert specs["welcome"].data() is not specs["welcome"].data()  # fresh copy every time


def test_module_off_hides_its_templates(event):
    assert "program-stage" in {s.key for s in gallery.available(event)}
    modules.set_event(event, "program", False)
    keys = {s.key for s in gallery.available(event)}
    assert "program-stage" not in keys and "welcome" in keys
    assert gallery.get(event, "program-stage") is None


def test_gallery_page_and_use(client, admin, event, monkeypatch):
    monkeypatch.setitem(registry.ensure_loaded().layout_templates, "x-plugin", LayoutTemplateSpec(
        key="x-plugin", name="From a plugin", category="Plugins", data=lambda: layout_format.starter()))
    login_2fa(client, admin)
    page = client.get("/e/demo/content/templates/")
    assert page.status_code == 200
    html = page.content.decode()
    assert 'data-preview-layout="welcome"' in html and "From a plugin" in html
    cfg = json.loads(re.search(r'<script id="preview-config" type="application/json">(.*?)</script>', html,
                               re.S).group(1))
    assert set(cfg["layouts"]) >= {"welcome", "x-plugin"} and cfg["vars"]["event"]["name"] == "Demo Camp"
    r = client.post("/e/demo/content/templates/", {"template": "info-board", "name": "Foyer info"})
    layout = Layout.objects.get(event=event, name="Foyer info")
    assert r.status_code == 302 and r["Location"].endswith(f"/content/layouts/{layout.pk}/edit/")
    assert layout.key == "foyer-info" and layout.data == gallery.info_board()
    client.post("/e/demo/content/templates/", {"template": "info-board", "name": "Foyer info"})
    assert Layout.objects.filter(event=event, key="foyer-info-2").exists()  # unique key
    r = client.post("/e/demo/content/templates/", {"template": "nope", "name": "X"})
    assert r.status_code == 200 and not Layout.objects.filter(name="X").exists()
    assert audit_url(client, "/e/demo/content/templates/") == []


def test_use_needs_content_edit(client, user, event):
    from apps.events import services as event_services
    from apps.events.models import Role

    event_services.assign_role(event, user, Role.objects.get(event=event, key="viewer"))
    login_2fa(client, user)
    r = client.post("/e/demo/content/templates/", {"template": "welcome", "name": "Nope"})
    assert r.status_code in (403, 404)
    assert not Layout.objects.filter(name="Nope").exists()
