# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.core.models import AuditLog
from apps.events.models import Event
from conftest import login_2fa


def bearer(user, scopes=(), event=None, two_factor=False, **kw):
    _tok, raw = ServiceToken.issue(name="t", owner=user, scopes=list(scopes), event=event, created_with_2fa=two_factor,
                                   **kw)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    return c


@pytest.mark.django_db
def test_health_and_auth(admin):
    c = APIClient()
    assert c.get("/api/v1/health/").json()["status"] == "ok"
    assert c.get("/api/v1/me/").status_code in (401, 403)
    c.credentials(HTTP_AUTHORIZATION="Bearer evac_nope")
    assert c.get("/api/v1/me/").status_code == 401
    me = bearer(admin).get("/api/v1/me/").json()
    assert me["email"] == admin.email and me["token"]["name"] == "t"


@pytest.mark.django_db
def test_token_expiry_inactive_owner_and_last_used(member):
    expired = bearer(member, expires_at=timezone.now() - dt.timedelta(minutes=1))
    assert expired.get("/api/v1/me/").status_code == 401
    ok = bearer(member)
    assert ok.get("/api/v1/me/").status_code == 200
    assert ServiceToken.objects.filter(last_used_at__isnull=False).exists()
    member.is_active = False
    member.save()
    assert ok.get("/api/v1/me/").status_code == 401


@pytest.mark.django_db
def test_scopes(member, event):
    ro = bearer(member, ["events:read"])
    assert ro.get("/api/v1/events/").status_code == 200
    assert ro.get("/api/v1/venues/").status_code == 403
    assert ro.patch("/api/v1/events/demo/", {"name": "x"}).status_code == 403
    tok = ServiceToken(scopes=["venues:write"])
    assert tok.has_scope("venues:read") and tok.has_scope("venues:write") and not tok.has_scope("events:read")
    assert ServiceToken(scopes=["events:*"]).has_scope("events:write")


@pytest.mark.django_db
def test_events_visibility_and_update(member, orga, other, event):
    assert [e["slug"] for e in bearer(member).get("/api/v1/events/").json()["results"]] == ["demo"]
    assert bearer(other).get("/api/v1/events/").json()["results"] == []
    assert bearer(member).patch("/api/v1/events/demo/", {"name": "x"}, format="json").status_code == 403
    # orga role requires 2FA: token minted without 2FA cannot manage
    assert bearer(orga).patch("/api/v1/events/demo/", {"name": "x"}, format="json").status_code == 403
    r = bearer(orga, two_factor=True).patch("/api/v1/events/demo/", {"name": "Renamed"}, format="json")
    assert r.status_code == 200 and Event.objects.get(slug="demo").name == "Renamed"
    assert AuditLog.objects.filter(action="event.updated").exists()
    bad = bearer(orga, two_factor=True).patch("/api/v1/events/demo/", {"end_date": "2020-01-01"}, format="json")
    assert bad.status_code == 400


@pytest.mark.django_db
def test_event_create_transition_export_clone_import(admin, member):
    c = bearer(admin, two_factor=True)
    r = c.post("/api/v1/events/", {"name": "API Event", "slug": "api-ev", "timezone": "UTC"}, format="json")
    assert r.status_code == 201
    assert bearer(member).post("/api/v1/events/", {"name": "x", "slug": "x"}, format="json").status_code == 403
    assert c.post("/api/v1/events/api-ev/transition/", {"state": "live"}, format="json").status_code == 400
    assert c.post("/api/v1/events/api-ev/transition/", {"state": "setup"}, format="json").json()["state"] == "setup"
    data = c.get("/api/v1/events/api-ev/export/").json()
    assert data["event"]["slug"] == "api-ev"
    r = c.post("/api/v1/events/import/", {"data": data, "slug": "api-ev-2"}, format="json")
    assert r.status_code == 201 and r.json()["slug"] == "api-ev-2"
    assert c.post("/api/v1/events/import/", {"data": {"x": 1}}, format="json").status_code == 400
    r = c.post("/api/v1/events/api-ev/clone/", {"name": "Clone", "slug": "api-clone"}, format="json")
    assert r.status_code == 201


@pytest.mark.django_db
def test_token_bound_to_event(admin, member, event):
    from apps.events import services

    other = services.create_event(name="Other", slug="other", user=admin)
    services.assign_role(other, member, other.roles.get(key="viewer"))
    c = bearer(member, event=event)
    assert [e["slug"] for e in c.get("/api/v1/events/").json()["results"]] == ["demo"]
    assert c.get("/api/v1/events/other/roles/").status_code == 403


@pytest.mark.django_db
def test_roles_api(admin, event):
    c = bearer(admin, two_factor=True)
    roles = c.get("/api/v1/events/demo/roles/").json()["results"]
    assert {r["key"] for r in roles} >= {"admin", "viewer"}
    r = c.post("/api/v1/events/demo/roles/", {"key": "stage", "name": "Stage", "permissions": ["venues.*"]},
               format="json")
    assert r.status_code == 201 and "venues.manage" in r.json()["effective_permissions"]
    assert c.patch("/api/v1/events/demo/roles/stage/", {"require_2fa": True}, format="json").json()["require_2fa"]
    assert c.delete("/api/v1/events/demo/roles/stage/").status_code == 204
    assert c.delete("/api/v1/events/demo/roles/viewer/").status_code == 403
    assert bearer(admin).post("/api/v1/events/demo/roles/", {"key": "x", "name": "x"}, format="json").status_code == 403
    assert c.post("/api/v1/events/demo/roles/", {"key": "y", "name": "y", "permissions": "nope"},
                  format="json").status_code == 400


@pytest.mark.django_db
def test_members_api(admin, other, event):
    c = bearer(admin, two_factor=True)
    r = c.post("/api/v1/events/demo/members/assign/", {"email": other.email, "role": "crew"}, format="json")
    assert r.status_code == 201
    r = c.post("/api/v1/events/demo/members/assign/", {"email": "new@example.org", "role": "crew"}, format="json")
    assert r.json() == {"invited": "new@example.org"}
    r = c.post("/api/v1/events/demo/members/assign/", {"email": "nobody@example.org", "role": "crew", "invite": False},
               format="json")
    assert r.status_code == 404
    r = c.post("/api/v1/events/demo/members/assign/", {"email": other.email, "role": "crew", "scope_kind": "zone",
                                                       "scope_id": "nope"}, format="json")
    assert r.status_code == 400
    members = c.get("/api/v1/events/demo/members/").json()["results"]
    m = next(x for x in members if x["user"]["email"] == other.email)
    assert c.delete(f"/api/v1/events/demo/members/{m['id']}/").status_code == 204
    admin_m = next(x for x in members if x["user"]["email"] == admin.email)
    assert c.delete(f"/api/v1/events/demo/members/{admin_m['id']}/").status_code == 403  # last admin


@pytest.mark.django_db
def test_sensitive_role_assignment_needs_roles_permission(orga, other, event):
    c = bearer(orga, two_factor=True)
    assert c.post("/api/v1/events/demo/members/assign/", {"email": other.email, "role": "crew"},
                  format="json").status_code == 201
    assert c.post("/api/v1/events/demo/members/assign/", {"email": other.email, "role": "admin"},
                  format="json").status_code == 403


@pytest.mark.django_db
def test_modules_audit_registry_extensions(admin, member, event):
    c = bearer(admin, two_factor=True)
    rows = c.get("/api/v1/events/demo/modules/").json()
    assert any(r["key"] == "venues" and r["active"] for r in rows)
    rows = c.patch("/api/v1/events/demo/modules/venues/", {"event": False}, format="json").json()
    assert not next(r for r in rows if r["key"] == "venues")["active"]
    assert c.patch("/api/v1/events/demo/modules/core/", {"event": False}, format="json").status_code == 400
    assert c.patch("/api/v1/events/demo/modules/nope/", {"event": False}, format="json").status_code == 404
    assert bearer(member).patch("/api/v1/events/demo/modules/venues/", {"event": None},
                                format="json").status_code == 403
    audit = c.get("/api/v1/events/demo/audit/?action=module.toggled").json()["results"]
    assert audit and audit[0]["hash"]
    assert c.get("/api/v1/audit/verify/").json()["ok"]
    assert bearer(member).get("/api/v1/audit/verify/").status_code == 403
    reg = c.get("/api/v1/registry/").json()
    assert any(p["key"] == "events.roles" and p["sensitive"] for p in reg["permissions"])
    assert c.get("/api/v1/extensions/").json()[0]["key"] == "webhooks"
    assert c.get("/api/v1/extensions/?event=demo").status_code == 200
    assert bearer(member).get("/api/v1/extensions/").status_code == 403
    assert bearer(member).get("/api/v1/extensions/?event=demo").status_code == 403


@pytest.mark.django_db
def test_tokens_api(client, member, event):
    login_2fa(client, member)
    r = client.post("/api/v1/tokens/", {"name": "bot", "scopes": ["events:read"], "event": "demo"},
                    content_type="application/json")
    assert r.status_code == 201 and r.json()["token"].startswith("evac_") and r.json()["created_with_2fa"]
    tid = r.json()["id"]
    assert "token" not in client.get("/api/v1/tokens/").json()["results"][0] or \
        client.get("/api/v1/tokens/").json()["results"][0]["token"] is None
    raw = r.json()["token"]
    tc = APIClient()
    tc.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert tc.post("/api/v1/tokens/", {"name": "x"}, format="json").status_code == 403  # tokens cannot mint tokens
    assert client.delete(f"/api/v1/tokens/{tid}/").status_code == 204


@pytest.mark.django_db
def test_venue_api_scoping(admin, member, other, event, venue, role):
    from apps.events import services
    from apps.venues.models import Zone

    c = bearer(admin, two_factor=True)
    assert c.get("/api/v1/venues/").json()["results"][0]["slug"] == "hall"
    assert bearer(other).get("/api/v1/venues/").json()["results"] == []
    assert bearer(member).get("/api/v1/zones/?venue=hall").json()["count"] == 2
    zid = Zone.objects.get(name="North").pk
    assert bearer(member).patch(f"/api/v1/zones/{zid}/", {"name": "N"}, format="json").status_code == 403
    services.assign_role(event, other, role("orga"))  # orga needs 2FA
    oc = bearer(other, two_factor=True)
    r = oc.patch(f"/api/v1/zones/{zid}/", {"name": "N2"}, format="json")
    assert r.status_code == 200 and Zone.objects.get(pk=zid).name == "N2"
    r = oc.post("/api/v1/rooms/", {"venue": str(venue.pk), "name": "Kiosk", "zones": [str(zid)]}, format="json")
    assert r.status_code == 201
    r = oc.post("/api/v1/venues/", {"slug": "annex", "name": "Annex", "event": "demo"}, format="json")
    assert r.status_code == 201 and event.venues.filter(slug="annex").exists()
    assert bearer(member).post("/api/v1/venues/", {"slug": "x", "name": "X"}, format="json").status_code == 403
    from apps.venues.models import Venue

    foreign = Venue.objects.create(slug="foreign", name="Foreign")
    from apps.venues.models import Zone as Z

    fz = Z.objects.create(venue=foreign, name="F")
    r = oc.post("/api/v1/rooms/", {"venue": str(venue.pk), "name": "Bad", "zones": [str(fz.pk)]}, format="json")
    assert r.status_code == 400
    assert oc.delete(f"/api/v1/zones/{zid}/").status_code == 204


@pytest.mark.django_db
def test_openapi_schema(client, admin):
    r = client.get("/api/schema/")
    assert r.status_code == 200 and b"ServiceToken" in r.content
