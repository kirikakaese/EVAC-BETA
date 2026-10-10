# SPDX-License-Identifier: AGPL-3.0-or-later
"""Venue nodes (ADR-0036). Central and node share one test database here: the node's calls run with
``EVAC_MODE=node`` and reach central's views through the test client. scripts/node_sync_e2e.py runs the same
flow with two real servers and databases."""
import json
from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.test import Client, override_settings
from django.utils import timezone

from apps.accounts.twofactor import SESSION_KEY
from apps.core import modules
from apps.core.a11y import check_html
from apps.core.models import AuditLog
from apps.evacuation import feed, services
from apps.evacuation.models import EvacState, EventAlarm, StateChange
from apps.nodes import central, client, guard, keys, snapshot
from apps.nodes.models import Node, NodeEvent, NodeIdentity, OpLogEntry, ProxiedAction


class ClientTransport:
    """Node → central through Django's test client, signed like the real transport."""

    def __init__(self):
        self.c = Client()
        self.down = False

    def request(self, method, path, body=b"", headers=None):
        if self.down:
            raise client.Unreachable("down")
        ident = NodeIdentity.objects.get(pk=1)
        from apps.core import crypto

        full = client.API + path
        hdrs = {"HTTP_AUTHORIZATION": f"Node {crypto.decrypt(ident.token_encrypted)}"} if ident.token_encrypted else {}
        if ident.sign_private_encrypted:
            for k, v in keys.sign_request(crypto.decrypt(ident.sign_private_encrypted), method, full, body).items():
                hdrs["HTTP_" + k.upper().replace("-", "_")] = v
        for k, v in (headers or {}).items():
            hdrs["HTTP_" + k.upper().replace("-", "_")] = v
        fn = self.c.get if method == "GET" else self.c.post
        resp = fn(full, data=body, content_type="application/json", **hdrs) if method != "GET" else fn(full, **hdrs)
        content = b"".join(resp.streaming_content) if getattr(resp, "streaming", False) else resp.content
        return client.Resp(resp.status_code, {k: v for k, v in resp.items()}, content)


class EnrolTransport(ClientTransport):
    def request(self, method, path, body=b"", headers=None):
        resp = self.c.post(client.API + path, data=body, content_type="application/json")
        return client.Resp(resp.status_code, {}, resp.content)


@pytest.fixture(autouse=True)
def evac_on(db):
    modules.set_instance("evacuation", True)


@pytest.fixture
def node(admin):
    n, code = central.register("Hall A rack", actor=admin)
    with override_settings(EVAC_MODE="node"):
        client.enrol("http://central.test", code, transport=EnrolTransport())
    n.refresh_from_db()
    return n


@pytest.fixture
def held(event, node, admin):
    modules.set_event(event, "evacuation", True)
    co = central.checkout(event, node, actor=admin)
    t = ClientTransport()
    with override_settings(EVAC_MODE="node"):
        client.sync_once(t)
    return co, t


def node_mode():
    return override_settings(EVAC_MODE="node")


# ------------------------------------------------------------------------------------------- keys
def test_keys_sign_and_seal():
    pair = keys.generate()
    h = keys.sign_request(pair["sign_private"], "POST", "/x?a=1", b"{}", now=1000)
    assert keys.verify_request(pair["sign_public"], "POST", "/x?a=1", b"{}", h["X-EVAC-Node-Timestamp"],
                               h["X-EVAC-Node-Signature"], now=1000)
    assert not keys.verify_request(pair["sign_public"], "POST", "/x?a=2", b"{}", h["X-EVAC-Node-Timestamp"],
                                   h["X-EVAC-Node-Signature"], now=1000)
    assert not keys.verify_request(pair["sign_public"], "POST", "/x?a=1", b"{}", h["X-EVAC-Node-Timestamp"],
                                   h["X-EVAC-Node-Signature"], now=1000 + keys.MAX_SKEW + 1)
    assert not keys.verify_request(pair["sign_public"], "GET", "/", b"", "nope", "x")
    sealed = keys.seal(pair["box_public"], "s3cret")
    assert sealed.startswith(keys.SEALED) and keys.open_sealed(pair["box_private"], sealed) == "s3cret"
    with pytest.raises(ValueError):
        keys.open_sealed(keys.generate()["box_private"], sealed)
    with pytest.raises(ValueError):
        keys.open_sealed(pair["box_private"], "plain")


# ------------------------------------------------------------------------------------------- enrolment
def test_enrolment(admin):
    n, code = central.register("Rack", actor=admin)
    assert n.code_hash and not n.active
    with node_mode():
        with pytest.raises(ValueError):
            client.enrol("http://central.test", "wrong-code", transport=EnrolTransport())
        ident = client.enrol("http://central.test", code, transport=EnrolTransport())
    n.refresh_from_db()
    assert n.active and n.sign_public == ident.sign_public and str(ident.node_id) == str(n.pk)
    with pytest.raises(central.SyncError):  # the code is used up
        central.enrol(code, sign_public="x" * 43, box_public="y" * 43)
    assert central.authenticate("evacn_nope") is None and central.authenticate("other") is None
    central.new_code(n, actor=admin)
    central.revoke(n, actor=admin)
    assert not Node.objects.get(pk=n.pk).active
    assert AuditLog.objects.filter(action="node.enrolled").exists()


def test_api_needs_signed_requests(node):
    c = Client()
    assert c.get("/api/v1/node/events/").status_code == 401
    assert c.get("/api/v1/node/events/", HTTP_AUTHORIZATION="Node evacn_x").status_code == 401
    t = ClientTransport()
    with node_mode():
        assert t.request("GET", "events/").status == 200
    NodeIdentity.objects.filter(pk=1).update(sign_private_encrypted="")
    assert t.request("GET", "events/").status == 401  # token without signature


# ------------------------------------------------------------------------------------------- snapshot
def test_snapshot_version_and_seed(event, admin, zones):
    from apps.evacuation import alarmkey

    alarmkey.ensure(event)
    a = snapshot.build(event)
    b = snapshot.build(event)
    assert a["version"] == b["version"] and not a["seed"]
    assert "evacuation.evacstate" not in a["models"] and "venues.zone" in a["models"]
    services.change(event, "evacuate", actor=admin, check_perms=False)
    assert snapshot.build(event)["version"] == a["version"]  # live state does not change the configuration
    seed = snapshot.build(event, seed=True)
    assert seed["models"]["evacuation.evacstate"]
    zones["North"].name = "Nord"
    zones["North"].save()
    assert snapshot.build(event)["version"] != a["version"]
    with pytest.raises(ValueError):
        snapshot.apply({"format": 99})


def test_secrets_travel_sealed(event, admin, node):
    from apps.evacuation import alarmkey

    alarmkey.ensure(event)
    data = snapshot.build(event, box_public=node.box_public)
    row = data["models"]["evacuation.eventalarm"][0]
    assert row["fields"]["private_key_encrypted"].startswith(keys.SEALED)
    assert snapshot.build(event)["models"]["evacuation.eventalarm"][0]["fields"]["private_key_encrypted"] == ""
    from apps.core import crypto

    box = crypto.decrypt(NodeIdentity.objects.get().box_private_encrypted)
    with node_mode():
        snapshot.apply(data, box_private=box)
    assert alarmkey.export_private(event)  # still decrypts locally after the round trip


# ------------------------------------------------------------------------------------------- the whole flow
def test_checkout_sync_alarm_and_checkin(event, admin, node, zones):
    modules.set_event(event, "evacuation", True)
    co = central.checkout(event, node, actor=admin)
    with pytest.raises(central.SyncError):
        central.checkout(event, node, actor=admin)
    t = ClientTransport()
    with node_mode():
        first = client.sync_once(t)
    assert first["events"][0]["snapshot"] == "applied"
    ne = NodeEvent.objects.get(pk=event.pk)
    co.refresh_from_db()
    assert ne.seeded and co.seeded and co.snapshot_version == ne.snapshot_version
    with node_mode():
        assert client.sync_once(t)["events"][0].get("snapshot") in (None, "unchanged")
        # an alarm raised on site goes into the op-log ...
        services.change(event, "evacuate", zone=zones["North"], actor=admin, check_perms=False, reason="smoke")
        ops = OpLogEntry.objects.filter(event_id=event.pk, pushed_at__isnull=True)
        assert ops.filter(kind="upsert", model="evacuation.statechange").exists()
        assert ops.filter(kind="audit").exists()
        # ... and reaches central with the next round
        NodeEvent.objects.filter(pk=event.pk).update(snapshot_at=timezone.now())
        out = client.sync_once(t)
    assert out["events"][0]["pushed"] >= 2
    co.refresh_from_db()
    assert co.applied_seq == NodeEvent.objects.get(pk=event.pk).next_seq - 1
    imported = AuditLog.objects.filter(scope__node="Hall A rack").first()
    assert imported is not None and imported.scope["node_hash"]
    # central's control room forwards instead of changing
    r = services.zones_of(event)
    assert guard.remote(event)
    from apps.evacuation import triggers

    out = triggers.trigger(event, "attention", source="web", actor=admin, check_perms=False)
    assert out.result == "forwarded" and ProxiedAction.objects.filter(kind="evacuation.trigger").exists()
    with pytest.raises(Exception, match="venue node"):
        services.change(event, "attention", actor=admin, check_perms=False)
    with node_mode():
        done = client.sync_once(t)["events"][0]
    assert done["actions"] == 1
    act = ProxiedAction.objects.get(kind="evacuation.trigger")
    assert act.status == "done" and act.result["result"] == "executed"
    assert EvacState.objects.get(event=event, zone=None).state == "attention"
    # check-in: everything pushed, the alarm counter handed back, the node keeps a read-only copy
    seq_node = feed.current_seq(event)
    central.request_checkin(co, actor=admin)
    with node_mode():
        res = client.sync_once(t)["events"][0]
    assert res["checkin"] == "checked_in"
    co.refresh_from_db()
    assert co.state == "checked_in" and not guard.remote(event)
    assert EventAlarm.objects.get(event=event).seq > seq_node - 1
    with node_mode():
        assert guard.read_only_copy(event)
        with pytest.raises(Exception, match="checked in"):
            services.change(event, "normal", actor=admin, check_perms=False)
    assert StateChange.objects.filter(event=event).exists() and r.exists()


def test_offline_round_and_gaps(held, event, admin):
    co, t = held
    t.down = True
    with node_mode():
        services.change(event, "evacuate", actor=admin, check_perms=False)
        out = client.sync_once(t)
    assert out["error"] == "down"
    assert "unreachable" in NodeIdentity.objects.get().last_error
    t.down = False
    with node_mode():
        client.sync_once(t)
    assert not OpLogEntry.objects.filter(event_id=event.pk, pushed_at__isnull=True).exists()
    co.refresh_from_db()
    # replays and gaps are harmless
    assert central.apply_oplog(co, [{"seq": 1, "key": "x:1", "kind": "audit", "data": {}}]) == co.applied_seq
    gap = co.applied_seq + 5
    assert central.apply_oplog(co, [{"seq": gap, "key": f"g:{gap}", "kind": "audit", "data": {}}]) == co.applied_seq
    nxt = co.applied_seq + 1
    with pytest.raises(central.SyncError):
        central.apply_oplog(co, [{"seq": nxt, "key": "bad", "kind": "upsert", "model": "venues.zone",
                                  "data": {"model": "venues.zone", "pk": "x", "fields": {}}}])
    with pytest.raises(central.SyncError):
        central.apply_oplog(co, [{"seq": nxt, "key": "bad2", "kind": "frobnicate", "model": "evacuation.evacstate"}])
    other = Client().post(f"/api/v1/node/events/{event.pk}/oplog/", data="{}", content_type="application/json")
    assert other.status_code == 401


def test_force_checkin_and_lost_node(held, event, admin):
    co, t = held
    before = EventAlarm.objects.get(event=event).seq
    ProxiedAction.objects.create(checkout=co, kind="evacuation.trigger", payload={})
    central.force_checkin(co, actor=admin, reason="node burnt")
    assert ProxiedAction.objects.get().status == "expired"
    assert EventAlarm.objects.get(event=event).seq >= before + 1000
    with node_mode():
        client.sync_once(t)
    assert not NodeEvent.objects.get(pk=event.pk).checked_out
    assert AuditLog.objects.filter(action="node.checkin_forced", message__contains="node burnt").exists()
    with pytest.raises(central.SyncError):
        central.complete_checkin(co, final_seq=0)


def test_checkin_refused_while_oplog_incomplete(held, event):
    co, _t = held
    with pytest.raises(central.SyncError):
        central.complete_checkin(co, final_seq=co.applied_seq + 3)


def test_files_resume_and_verify(held, event, settings, tmp_path):
    co, t = held
    import hashlib
    import pathlib

    media = pathlib.Path(settings.MEDIA_ROOT)
    data = b"0123456789" * 1000
    (media / "venues" / "plans").mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(data).hexdigest()
    path = f"venues/plans/{sha}.png"
    (media / path).write_bytes(data)
    with mock.patch.object(snapshot, "files_of", return_value=[[path, sha]]):
        ne = NodeEvent.objects.get(pk=event.pk)
        ne.files = [[path, sha]]
        ne.save()
        (media / path).rename(media / (path + ".src"))
        (media / (path + ".src")).rename(media / path)  # keep a copy to serve
        served = (media / path).read_bytes()
        (media / path).unlink()
        (media / path).write_bytes(served)
        part = media / (path + ".part")
        # the node lost the file and has half of it already
        stash = media / "stash.bin"
        stash.write_bytes(served)
        (media / path).unlink()
        part.write_bytes(served[:4000])
        stash.rename(media / path)  # central's copy (same media root here)
        (media / path).rename(media / (path + ".central"))

        def central_copy(method, p, body=b"", headers=None):
            if "/files/" not in p:
                return ClientTransport.request(t, method, p, body, headers)
            start = int((headers or {}).get("Range", "bytes=0-")[6:-1] or 0)
            return client.Resp(206 if start else 200, {}, served[start:])

        with mock.patch.object(t, "request", side_effect=central_copy):
            assert client.fetch_files(t, ne) == 1
    assert (media / path).read_bytes() == data and not part.exists()
    # through the real endpoint: Range, 416 and unknown paths
    with mock.patch.object(snapshot, "files_of", return_value=[[path, sha]]):
        r = t.request("GET", f"events/{event.pk}/files/{path}", headers={"Range": "bytes=10-"})
        assert r.status == 206 and r.body == data[10:]
        assert t.request("GET", f"events/{event.pk}/files/{path}", headers={"Range": f"bytes={len(data)}-"}).status \
            == 416
        assert t.request("GET", f"events/{event.pk}/files/other.png").status == 404
        assert t.request("GET", f"events/{event.pk}/files/{path}").body == data


def test_bad_checksum_is_fetched_again(held, event, settings):
    co, t = held
    ne = NodeEvent.objects.get(pk=event.pk)
    ne.files = [["venues/plans/x.png", "0" * 64]]
    ne.save()
    with mock.patch.object(t, "request", return_value=client.Resp(200, {}, b"abc")):
        assert client.fetch_files(t, ne) == 0
    with mock.patch.object(t, "request", return_value=client.Resp(500, {}, b"")):
        assert client.fetch_files(t, ne) == 0


# ------------------------------------------------------------------------------------------- pages
def test_pages(admin_client, admin, event, node):
    r = admin_client.get("/settings/nodes/")
    assert r.status_code == 200 and check_html(r.content.decode()) == [] and "Hall A rack" in r.content.decode()
    r = admin_client.post("/settings/nodes/", {"what": "add", "name": "Hall B"})
    assert r.status_code == 200 and "Enrolment code" in r.content.decode()
    assert admin_client.post("/settings/nodes/", {"what": "add", "name": ""}).status_code == 302
    nb = Node.objects.get(name="Hall B")
    assert "Enrolment code" in admin_client.post("/settings/nodes/", {"what": "code", "pk": nb.pk}).content.decode()
    url = f"/e/{event.slug}/nodes/"
    r = admin_client.get(url)
    assert r.status_code == 200 and check_html(r.content.decode()) == []
    admin_client.post(url, {"what": "checkout", "node": str(node.pk)})
    assert central.checkout_of(event) is not None
    html = admin_client.get(url).content.decode()
    assert "checked out" in html and check_html(html) == []
    r = admin_client.post("/settings/nodes/", {"what": "revoke", "pk": node.pk}, follow=True)
    assert "check the node" in r.content.decode()
    admin_client.post(url, {"what": "checkin"})
    assert central.checkout_of(event).state == "checkin_requested"
    admin_client.post(url, {"what": "force", "reason": "test"})
    assert central.checkout_of(event) is None
    admin_client.post(url, {"what": "checkout", "node": "nope"})
    assert central.checkout_of(event) is None
    with override_settings(EVAC_MODE="node"):
        assert "This is a venue node" in admin_client.get("/settings/nodes/").content.decode()
        assert "On this node" in admin_client.get(url).content.decode()
    session = admin_client.session
    del session[SESSION_KEY]
    session.save()
    assert admin_client.post(url, {"what": "checkout", "node": str(node.pk)}).status_code == 403


def test_command(node, event, admin):
    with pytest.raises(CommandError):
        call_command("evac_node", "status")  # central mode
    with node_mode():
        out = StringIO()
        call_command("evac_node", "status", stdout=out)
        assert "Hall A rack" in out.getvalue()
        with pytest.raises(CommandError):
            call_command("evac_node", "enrol")
        with mock.patch.object(client, "sync_once", return_value={"events": []}):
            out = StringIO()
            call_command("evac_node", "sync", stdout=out)
            assert json.loads(out.getvalue()) == {"events": []}
        with mock.patch.object(client, "enrol", side_effect=ValueError("bad code")), pytest.raises(CommandError):
            call_command("evac_node", "enrol", "--central", "http://x", "--code", "y")
        NodeIdentity.objects.all().delete()
        with pytest.raises(CommandError):
            call_command("evac_node", "sync")
        with pytest.raises(ValueError):
            client.sync_once(ClientTransport())
