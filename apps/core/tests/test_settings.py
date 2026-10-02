# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from apps.core import settings_schema, settings_store
from apps.core.forms import SchemaForm

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": 10, "default": "Hi"},
        "count": {"type": "integer", "minimum": 0, "default": 3},
        "on": {"type": "boolean", "default": False},
        "color": {"type": "string", "format": "color"},
        "mode": {"type": "string", "enum": ["a", "b"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "pick": {"type": "array", "items": {"type": "string", "enum": ["x", "y"]}},
        "url": {"type": "string", "format": "uri"},
        "ratio": {"type": "number"},
        "notes": {"type": "string", "x-widget": "textarea"},
    },
}


def test_resolve_inheritance_and_provenance():
    r = settings_schema.resolve(SCHEMA, [("instance", {"count": 5}), ("event", {"title": "Ev", "unknown": 1})])
    assert r.values["title"] == "Ev" and r.values["count"] == 5 and r.values["on"] is False
    assert r.source == {"title": "event", "count": "instance", "on": "default"}
    assert r.overridden_at("event") == ["title"]
    assert "unknown" not in r.values


def test_validate():
    assert settings_schema.validate(SCHEMA, {"count": 1}) == []
    errs = settings_schema.validate(SCHEMA, {"count": -1, "bogus": 1})
    assert any("count" in e for e in errs) and any("bogus" in e.lower() or "additional" in e.lower() for e in errs)


def test_coerce():
    assert settings_schema.coerce({"type": "boolean"}, "on") is True
    assert settings_schema.coerce({"type": "integer"}, "7") == 7
    assert settings_schema.coerce({"type": "integer"}, "x") == "x"
    assert settings_schema.coerce({"type": "number"}, "1.5") == 1.5
    assert settings_schema.coerce({"type": "array"}, "a, b\nc") == ["a", "b", "c"]


def test_schema_form_with_inherit():
    resolved = settings_schema.resolve(SCHEMA, [("instance", {"count": 5})])
    form = SchemaForm({"title": "Mine", "count": "9", "count__inherit": "on", "tags": "a\nb", "pick": ["x"],
                       "title__inherit": "", "mode": "a", "mode__inherit": ""},
                      schema=SCHEMA, inherit=True, resolved=resolved, level="event")
    for name in ("on", "color", "url", "ratio", "notes", "tags", "pick"):
        form.data = {**form.data, f"{name}__inherit": "on"}
    assert form.is_valid(), form.errors
    assert form.values() == {"title": "Mine", "mode": "a"}
    assert len(form.rows()) == len(SCHEMA["properties"])


def test_schema_form_rejects_invalid():
    schema = {"type": "object", "properties": {"title": SCHEMA["properties"]["title"]}}
    form = SchemaForm({"title": "x" * 20}, schema=schema)
    assert not form.is_valid()


@pytest.mark.django_db
def test_store_save_and_resolve(event, admin):
    settings_store.save("general", "instance", "", {"retention_days": 30}, user=admin)
    settings_store.save("general", "event", str(event.pk), {"support_contact": "desk@x"}, user=admin, event=event)
    r = settings_store.resolve("general", event=event)
    assert r.values["retention_days"] == 30 and r.source["retention_days"] == "instance"
    assert r.values["support_contact"] == "desk@x" and r.source["support_contact"] == "event"
    assert settings_store.get("general")["support_contact"] == ""
    with pytest.raises(settings_store.SettingsError):
        settings_store.save("general", "event", str(event.pk), {"retention_days": -1})
    with pytest.raises(settings_store.SettingsError):
        settings_store.save("general", "screen", "x", {})
    settings_store.save("general", "event", str(event.pk), {}, user=admin)
    assert settings_store.raw("general", "event", str(event.pk)) == {}
    with pytest.raises(KeyError):
        settings_store.namespace("nope")


@pytest.mark.django_db
def test_settings_pages(admin_client, event):
    r = admin_client.post("/settings/general/general/", {"support_contact": "info", "retention_days": "10",
                                                         "heartbeat_seconds": "10"})
    assert r.status_code == 302
    assert settings_store.get("general")["retention_days"] == 10
    data = {"support_contact": "event desk", "retention_days__inherit": "on", "heartbeat_seconds__inherit": "on",
            "public_pages__inherit": "on"}
    r = admin_client.post("/e/demo/settings/s/general/", data)
    assert r.status_code == 302
    vals = settings_store.resolve("general", event=event)
    assert vals.values["support_contact"] == "event desk" and vals.source["retention_days"] == "instance"
    page = admin_client.get("/e/demo/settings/s/general/").content.decode()
    assert "overridden here" in page and "inherited from instance" in page
    assert admin_client.get("/e/demo/settings/s/nope/").status_code == 404
