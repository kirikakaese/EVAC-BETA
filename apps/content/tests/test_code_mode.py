# SPDX-License-Identifier: AGPL-3.0-or-later
"""Code mode: format, the content.code permission, audit, CSP nonce on pages that render code."""
import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.content import layout_format as lf
from apps.content import services
from apps.core.models import AuditLog
from apps.events import services as event_services
from conftest import login_2fa

CODE = {"id": "c1", "type": "code", "frame": {"x": 0, "y": 0, "w": 50, "h": 50},
        "props": {"html": "<p id=t></p>", "css": "p{color:red}", "js": "evac.onData(d => t.textContent = d.now)",
                  "data": ["time"]}}


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


def with_code(layout_data, **props):
    el = {**CODE, "props": {**CODE["props"], **props}}
    return {**layout_data, "elements": [*layout_data["elements"], el]}


@pytest.fixture
def designer(event, admin):
    """May edit layouts, but not write code."""
    role = event.roles.create(key="designer", name="Designer", permissions=["content.*", "!content.code"])
    u = User.objects.create_user(email="designer@example.org", password="pw-designer-123")
    event_services.assign_role(event, u, role, actor=admin)
    return u


def test_format():
    data = with_code(lf.empty())
    assert lf.validate(data) == []
    assert lf.validate(with_code(lf.empty(), data=["cookies"]))
    assert lf.validate(with_code(lf.empty(), js="x" * 100_001))
    assert lf.validate(with_code(lf.empty(), assets=["not-a-uuid"]))
    assert lf.code_changed(lf.empty(), data)
    assert not lf.code_changed(data, data)
    assert not lf.code_changed(data, lf.empty())  # removing code is not writing code
    moved = {**data, "elements": [{**data["elements"][0], "frame": {"x": 5, "y": 5, "w": 50, "h": 50}}]}
    assert not lf.code_changed(data, moved)
    assert lf.code_changed(data, with_code(lf.empty(), data=["time", "event"]))


@pytest.mark.django_db
def test_only_code_writers_add_or_change_code(admin, event, designer):
    layout = services.create_layout(event, name="Board", key="board", actor=designer)
    with pytest.raises(ValidationError, match="content.code"):
        services.save_layout(layout, with_code(layout.data), actor=designer)
    with pytest.raises(ValidationError):
        services.create_layout(event, name="Sneaky", key="sneaky", actor=designer, data=with_code(lf.empty()))
    # an admin writes code; it is audit-logged with a hash, not the code itself
    services.save_layout(layout, with_code(layout.data), actor=admin)
    entry = AuditLog.objects.get(action="layout.code_changed")
    assert entry.changes["c1"]["data"] == ["time"] and "evac.onData" not in str(entry.changes)
    # the designer may still move the code element or edit other elements, and remove the code element
    data = layout.data
    moved = {**data, "elements": [e if e["id"] != "c1" else {**e, "frame": {**e["frame"], "x": 10}}
                                  for e in data["elements"]]}
    services.save_layout(layout, moved, actor=designer)
    v_with_code = layout.versions.get(number=layout.version)
    services.save_layout(layout, {**moved, "elements": [e for e in moved["elements"] if e["id"] != "c1"]},
                         actor=designer)
    # ... but not bring changed code back by restoring an old version when the code differs from now
    with pytest.raises(ValidationError):
        services.rollback_layout(layout, v_with_code, actor=designer)
    services.rollback_layout(layout, v_with_code, actor=admin)
    assert services.may_write_code(None, event)
    assert not services.may_write_code(designer, None) and services.may_write_code(admin, None)


@pytest.mark.django_db
def test_editor_and_save_endpoint(client, admin, event, designer):
    layout = services.create_layout(event, name="Board", key="board", actor=admin, data=with_code(lf.empty()))
    login_2fa(client, designer)
    page = client.get(f"/e/demo/content/layouts/{layout.pk}/edit/")
    csp = page["Content-Security-Policy"]
    assert "script-src 'self' 'nonce-" in csp
    assert f'nonce="{page.context["csp_nonce"]}"' in page.content.decode()
    assert '"canCode": false' in page.content.decode()
    r = client.post(f"/e/demo/content/layouts/{layout.pk}/save/",
                    {"data": with_code(lf.empty(), js="alert(1)"), "version": layout.version},
                    content_type="application/json")
    assert r.status_code == 400 and "content.code" in r.json()["errors"][0]
    login_2fa(client, admin)
    assert '"canCode": true' in client.get(f"/e/demo/content/layouts/{layout.pk}/edit/").content.decode()
    # pages that do not render layouts keep the strict policy without a script nonce
    other = client.get("/e/demo/content/layouts/")["Content-Security-Policy"]
    assert "script-src 'self';" in other


@pytest.mark.django_db
def test_player_page_allows_code_frames(client):
    r = client.get("/player/")
    assert "script-src 'self' 'nonce-" in r["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r["Content-Security-Policy"]
    assert 'type="module" nonce="' in r.content.decode()
