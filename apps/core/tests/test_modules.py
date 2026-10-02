# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.http import Http404
from django.test import RequestFactory

from apps.core import modules
from apps.core.plugins import ModuleSpec
from apps.core.registry import registry


@pytest.mark.django_db
def test_instance_and_event_toggles(event, admin):
    assert modules.is_enabled("venues", event)
    modules.set_event(event, "venues", False, user=admin)
    assert not modules.is_enabled("venues", event)
    assert modules.is_enabled("venues")  # instance unaffected
    modules.set_event(event, "venues", None, user=admin)
    assert modules.is_enabled("venues", event)
    modules.set_instance("venues", False, user=admin)
    assert not modules.is_enabled("venues", event)
    modules.set_event(event, "venues", True, user=admin)  # event cannot override an instance "off"
    assert not modules.is_enabled("venues", event)


@pytest.mark.django_db
def test_required_modules_cannot_be_disabled(event):
    assert modules.is_enabled("core", event)
    with pytest.raises(ValueError):
        modules.set_instance("core", False)
    with pytest.raises(ValueError):
        modules.set_event(event, "core", False)


@pytest.mark.django_db
def test_dependencies(event, monkeypatch):
    monkeypatch.setitem(registry.modules, "child", ModuleSpec(key="child", name="Child", depends_on=("venues",)))
    assert modules.is_enabled("child", event)
    modules.set_event(event, "venues", False)
    assert not modules.is_enabled("child", event)
    row = next(r for r in modules.status(event) if r["spec"].key == "child")
    assert row["missing_deps"] == ["venues"]
    assert not modules.is_enabled("unknown-module")


@pytest.mark.django_db
def test_require_module_decorator(event):
    @modules.require_module("venues")
    def view(request, event=None):
        return "ok"

    req = RequestFactory().get("/")
    assert view(req, event=event) == "ok"
    modules.set_event(event, "venues", False)
    event = type(event).objects.get(pk=event.pk)
    with pytest.raises(Http404):
        view(req, event=event)


@pytest.mark.django_db
def test_module_pages_toggle(admin_client, event):
    r = admin_client.post("/settings/modules/", {"key": "venues", "value": "off"})
    assert r.status_code == 302 and not modules.instance_enabled("venues")
    admin_client.post("/settings/modules/", {"key": "venues", "value": "on"})
    r = admin_client.post("/e/demo/settings/modules/", {"key": "venues", "value": "off"})
    assert r.status_code == 302
    assert not modules.is_enabled("venues", type(event).objects.get(pk=event.pk))
    # switched-off module: its pages 404
    assert admin_client.get("/e/demo/venues/").status_code == 404
    admin_client.post("/e/demo/settings/modules/", {"key": "venues", "value": "inherit"})
    assert admin_client.get("/e/demo/venues/").status_code == 200


@pytest.mark.django_db
def test_module_page_permissions(client, member, event):
    client.force_login(member)
    assert client.get("/settings/modules/").status_code == 403
    assert client.get("/e/demo/settings/modules/").status_code == 403
