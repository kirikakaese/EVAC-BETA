# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from unittest import mock

import pytest

from apps.announcements import services as ann_services
from apps.announcements.models import Announcement, Delivery, Level
from apps.core import modules, settings_store
from apps.core.a11y import audit_url
from apps.core.models import Notification
from apps.core.registry import registry
from apps.evacuation import services as evac
from apps.evacuation.models import EvacRequest, EvacState
from apps.events import services as event_services
from apps.extensions import services as ext
from apps.extensions.models import ExtensionLog
from apps.widgets.models import CustomWidget, Feed
from extensions.dial import inbound, link, outbound, recordings, roles, sources, whisper
from extensions.dial.client import Client, Rejected, Temporary
from extensions.dial.models import Broadcast, DectAlert, Recording, RoleMapping, Snapshot

from .conftest import BASE


@pytest.fixture
def acknowledged(event):
    modules.set_event(event, "evacuation", True)
    modules.acknowledge(event, "evacuation")
    settings_store.save("evacuation", "event", str(event.pk), {"model": "staged"}, event=event)
    return event


FEATURES = ("trigger", "evacuation_broadcast", "announcements", "recordings", "data_sources")


def resave(cfg, settings_values, features):
    return ext.save_config(cfg, settings_values=settings_values, secret_values={},
                           features={**dict.fromkeys(FEATURES, True), **features}, enabled=True)


def tf_client(client, user):
    from apps.accounts.twofactor import SESSION_KEY

    client.force_login(user)
    s = client.session
    s[SESSION_KEY] = "2026-01-01T00:00:00"
    s.save()
    return client


# ------------------------------------------------------------------ 4.1 link + test connection
def test_registered_as_plugin():
    r = registry.ensure_loaded()
    spec = r.extensions["dial"]
    assert spec.scope == "event" and spec.signature_header == "X-DIAL-Signature"
    assert spec.event_header == "X-DIAL-Event" and spec.delivery_id is inbound.delivery_id
    assert {"dial.phonebook", "dial.numbers", "dial.pages", "dial.dect"} <= set(r.data_sources)
    assert {"dial_call", "dial_sms"} <= set(r.notification_channels) and "dial" in r.evac_triggers
    assert "dial.dect_alert" in r.webhook_events and "dial.status" in r.permission_keys()


def test_connection_ok(link, dial):
    result = link_test(link)
    assert result.ok and "Connected to DIAL as evac" in result.message and "PBX: ok" in result.message
    health = dial.calls[0]
    assert health[1] == "health/" and health[2] == {"event": "camp"}
    assert dial.calls[1][4]["Authorization"] == "Bearer dial_secret_token"


def link_test(cfg):
    return link.test_connection(cfg)


def test_connection_problems(link, dial):
    dial.routes[("GET", "health/")] = (404, {"ok": False, "error": "unknown event"})
    assert "does not know the event" in link_test(link).message
    dial.routes[("GET", "health/")] = (503, {"ok": False, "pbx": {"ok": False, "error": "ARI down"},
                                             "dect": {"ok": True}})
    dial.routes[("GET", "me/")] = (401, {"detail": "Invalid service token."})
    r = link_test(link)
    assert not r.ok and "refused the service token" in r.message
    dial.routes[("GET", "me/")] = (200, {"username": "admin", "service_account": None})
    r = link_test(link)
    assert r.ok and "PBX: ARI down" in r.message  # DIAL is up, the venue PBX is not
    link.settings["event"] = ""
    assert "Set the DIAL event slug" in link_test(link).message


def test_connection_without_token_and_offline(link, dial):
    link.set_secrets({})
    assert "no service token" in link_test(link).message
    with mock.patch("extensions.dial.client.requests.request", side_effect=__import__("requests").ConnectionError):
        assert "DIAL did not answer" in link_test(link).message


def test_client_errors_never_leak_token(dial):
    c = Client(BASE, "dial_tok", "camp")
    dial.routes[("GET", "x/")] = (500, {"detail": "boom"})
    with pytest.raises(Temporary) as exc:
        c.get("x/")
    assert "dial_tok" not in str(exc.value) and "boom" in str(exc.value)
    dial.routes[("GET", "x/")] = (403, {"detail": "orga role required"})
    with pytest.raises(Rejected) as exc:
        c.get("x/")
    assert exc.value.status == 403
    with pytest.raises(Rejected):
        Client("", "t", "camp").get("x/")
    with pytest.raises(Rejected):
        c.download("https://elsewhere.example/x.wav")
    with pytest.raises(Rejected):
        c.download(BASE + "/media/missing.wav")
    assert c.results("dect/rfps/") and c.results("events/camp/members/", limit=2) == [
        {"user": "alice", "role": "orga"}, {"user": "zed", "role": "user"}]


def test_settings_page_and_status_page(client, admin, event, link, dial):
    tf_client(client, admin)
    page = client.get(f"/e/{event.slug}/settings/extensions/dial/")
    assert page.status_code == 200 and b"DIAL event slug" in page.content
    assert client.get(f"/e/{event.slug}/settings/extensions/dial/x/").url == f"/e/{event.slug}/dial/"
    page = client.get(f"/e/{event.slug}/dial/")
    assert page.status_code == 200 and f"/api/v1/extensions/dial/{link.pk}/webhook/".encode() in page.content
    assert b"events:read" in page.content


def test_status_page_without_link(client, admin, event):
    tf_client(client, admin)
    page = client.get(f"/e/{event.slug}/dial/")
    assert page.status_code == 200 and b"not linked" in page.content


# ------------------------------------------------------------------ 4.2 inbound
def test_signature_and_idempotency(post_hook, link, acknowledged, dial):
    data = {"event": "camp", "number": "112", "caller": "4711", "incident_id": 5, "at": "2026-07-01T12:00:00Z"}
    assert post_hook("emergency.triggered", data, secret="wrong").status_code == 401
    first = post_hook("emergency.triggered", data)
    assert first.status_code == 200 and first.json()["result"] == "armed"
    again = post_hook("emergency.triggered", data)  # DIAL's retry: new sent_at, same data
    assert again.json()["duplicate"] is True and EvacRequest.objects.count() == 1


def test_delivery_id():
    a = inbound.delivery_id({}, b"", {"type": "x", "sent_at": "1", "data": {"b": 1, "a": 2}})
    b = inbound.delivery_id({}, b"", {"type": "x", "sent_at": "2", "data": {"a": 2, "b": 1}})
    assert a == b and a.startswith("dial:x:") and inbound.delivery_id({}, b"", []) == ""


def test_emergency_call_goes_through_policy(post_hook, acknowledged, dial):
    r = post_hook("emergency.triggered", {"event": "camp", "number": "112", "caller": "4711", "incident_id": 9})
    assert r.json()["result"] == "armed"
    req = EvacRequest.objects.get()
    assert req.source == "dial" and req.state == "staff_alert" and "112" in req.reason and "4711" in req.reason
    assert not EvacState.objects.filter(event=acknowledged).exclude(state="normal").exists()


def test_emergency_policy_execute(post_hook, acknowledged, dial, admin):
    from apps.evacuation import triggers
    from apps.evacuation.models import EvacPolicy

    EvacPolicy.objects.create(event=acknowledged, source="dial", action="execute")
    r = post_hook("emergency.triggered", {"event": "camp", "number": "110", "incident_id": 1})
    assert r.json()["result"] == "executed"
    assert evac.statuses(acknowledged)[0].state == "staff_alert"
    assert "dial" in dict(triggers.sources())


def test_emergency_stage_fallback(link, acknowledged):
    settings_store.save("evacuation", "event", str(acknowledged.pk), {"model": "simple"}, event=acknowledged)
    assert inbound._stage(link, acknowledged) == "evacuate"
    settings_store.save("evacuation", "event", str(acknowledged.pk), {"model": "staged", "staff_alert_enabled": False},
                        event=acknowledged)
    assert inbound._stage(link, acknowledged) == "attention"


def test_emergency_ignored_and_refused(post_hook, link, event, dial):
    assert post_hook("emergency.triggered", {"kind": "broadcast", "broadcast_id": 3}).json()["ignored"] == "broadcast"
    r = post_hook("emergency.triggered", {"event": "other", "number": "112"})
    assert r.json()["ignored"] == "other event"
    # the evacuation module is off for the event
    assert post_hook("emergency.triggered", {"number": "112", "incident_id": 1}).status_code == 409
    modules.set_event(event, "evacuation", True)
    r = post_hook("emergency.triggered", {"number": "112", "incident_id": 2})
    assert r.status_code == 409 and "safety statement" in r.json()["error"]
    modules.acknowledge(event, "evacuation")
    resave(link, {**link.settings, "emergency_numbers": "110"}, {})
    assert post_hook("emergency.triggered", {"number": "112", "incident_id": 3}).json()["ignored"] == "number"
    resave(link, link.settings, {"trigger": False})
    assert post_hook("emergency.triggered", {"number": "110", "incident_id": 4}).json()["ignored"] == \
        "trigger switched off"
    assert not EvacRequest.objects.exists()
    assert post_hook("something.else", {}).json()["ignored"] == "something.else"


def test_webhook_needs_event_config(event, db):
    cfg = ext.get_or_new(registry.get_extension("dial"), None)
    result = inbound.handle(cfg, {}, b"", {"type": "x"})
    assert result.status == 400
    cfg = ext.get_or_new(registry.get_extension("dial"), event)
    assert inbound.handle(cfg, {}, b"", []).status == 400


def test_dect_alert(post_hook, event, admin, dial, link):
    from apps.events.models import Role

    r = post_hook("dect.rfp.down", {"id": 3, "kind": "rfp.down", "severity": "critical", "message": "RFP-2 down",
                                    "rfp": "RFP-2", "event": "camp", "at": "2026-07-01T12:00:00+00:00"})
    assert r.status_code == 200
    alert = DectAlert.objects.get()
    assert alert.kind == "rfp.down" and alert.rfp == "RFP-2"
    assert Notification.objects.filter(user=admin, title__contains="rfp.down").exists()
    assert ExtensionLog.objects.filter(config=link, message__contains="DECT rfp.down").exists()
    snap = Snapshot.objects.get(config=link, key="dect")
    assert snap.data["down"] == 1 and snap.data["up"] == 1 and snap.data["alerts"][0]["kind"] == "rfp.down"
    post_hook("dect.rfp.up", {"id": 4, "kind": "rfp.up", "severity": "info", "rfp": "RFP-2"})
    assert Notification.objects.filter(user=admin).count() == 1  # recovery: logged, not notified
    assert Role.objects.filter(event=event).exists()


def test_page_updated_refreshes_feeds(post_hook, event, dial, link):
    modules.set_event(event, "widgets", True)
    feed = Feed.objects.create(event=event, name="pages", kind=Feed.Kind.SOURCE, source="dial.pages")
    assert post_hook("page.updated", {"id": 1, "updated_at": "x", "action": "update"}).json()["refresh"] == "pages"
    feed.refresh_from_db()
    assert feed.status == "ok" and feed.snapshot["items"][0]["text"] == "SSID camp & more\none"


# ------------------------------------------------------------------ recordings
@pytest.fixture
def speech_dir(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path / "tts"


def test_recording_to_approval_queue(post_hook, event, link, dial, speech_dir, admin):
    r = post_hook("announcement.recorded", {"extension": "4000", "event": "camp", "audio": "ivr/camp/4000/phone-a.wav",
                                            "file": "/var/rec/a", "duration": 12, "imported": True})
    assert r.status_code == 200
    rec = Recording.objects.get()
    assert rec.status == "imported" and rec.speech_file.endswith((".wav", ".m4a"))
    assert (speech_dir / rec.speech_file).is_file()
    ann = rec.announcement
    assert ann.status == Announcement.Status.PENDING and ann.speech_recorded and ann.speech_status == "ready"
    assert "4000" in ann.title and "No transcript" in rec.detail
    assert ("DOWNLOAD", "/media/ivr/camp/4000/phone-a.wav") == dial.calls[-1][:2]
    assert dial.calls[-1][4]["Authorization"] == "Bearer dial_secret_token"
    # approving does not replace the recording with synthetic speech
    ann_services.queue_speech(ann)
    ann.refresh_from_db()
    assert ann.speech_file == rec.speech_file and ann.speech_status == "ready"


def test_recording_auto_publish_with_transcript(post_hook, event, link, dial, speech_dir):
    resave(link, {**link.settings, "auto_publish_extensions": "4000, 4001"}, {})
    with mock.patch.object(whisper, "transcribe", return_value="Lost child at gate two. Please help."):
        post_hook("announcement.recorded", {"extension": "4000", "audio": "ivr/camp/4000/phone-a.wav",
                                            "duration": 5})
    ann = Recording.objects.get().announcement
    assert ann.title == "Lost child at gate two" and ann.body.startswith("Lost child")
    assert ann.status in (Announcement.Status.LIVE, Announcement.Status.SCHEDULED)


def test_recording_without_audio(post_hook, event, link, dial, speech_dir):
    post_hook("announcement.recorded", {"extension": "4000", "audio": None, "file": "/pbx/x", "duration": 3})
    rec = Recording.objects.get()
    assert rec.status == "imported" and not rec.speech_file and "PBX only" in rec.detail
    assert not rec.announcement.speech_recorded


def test_recording_download_fails(post_hook, event, link, dial, speech_dir):
    dial.files.clear()
    post_hook("announcement.recorded", {"extension": "4000", "audio": "ivr/camp/4000/phone-a.wav"})
    rec = Recording.objects.get()
    assert rec.status == "imported" and "could not be fetched" in rec.detail


def test_recording_not_wav(event, link, dial, speech_dir):
    with pytest.raises(Rejected):
        recordings.store(b"not a wav file at all")


def test_recording_announcements_off(post_hook, event, link, dial, speech_dir):
    modules.set_event(event, "announcements", False)
    post_hook("announcement.recorded", {"extension": "4000", "audio": "ivr/camp/4000/phone-a.wav"})
    assert Recording.objects.get().status == "failed"
    resave(link, link.settings, {"recordings": False})
    assert post_hook("announcement.recorded", {"extension": "4001"}).json()["ignored"] == "recordings switched off"


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="needs ffmpeg")
def test_whisper_transcribes(settings, tmp_path):
    fake = tmp_path / "whisper-cli"
    # whisper.cpp writes <-of>.txt; this stand-in does the same
    fake.write_text('#!/bin/sh\nwhile [ "$1" != "-of" ]; do shift; done\nprintf "  Hello\\n  world. " > "$2.txt"\n')
    fake.chmod(0o755)
    (tmp_path / "model.bin").write_bytes(b"x")
    settings.EVAC_WHISPER_BINARY, settings.EVAC_WHISPER_MODEL = str(fake), str(tmp_path / "model.bin")
    import struct

    pcm = b"\x00\x00" * 800
    wav = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2,
                                                                                 16) + b"data" + struct.pack(
        "<I", len(pcm)) + pcm
    (tmp_path / "a.wav").write_bytes(wav)
    assert whisper.status()[0] and whisper.transcribe(tmp_path / "a.wav") == "Hello world."
    fake.write_text("#!/bin/sh\nexit 3\n")
    with pytest.raises(whisper.TranscriptionError):
        whisper.transcribe(tmp_path / "a.wav")
    (tmp_path / "b.wav").write_bytes(b"garbage")
    with pytest.raises(whisper.TranscriptionError):
        whisper.transcribe(tmp_path / "b.wav")


def test_whisper_status(settings, tmp_path):
    settings.EVAC_WHISPER_BINARY = str(tmp_path / "missing")
    assert not whisper.status()[0]
    with pytest.raises(whisper.TranscriptionError):
        whisper.transcribe(tmp_path / "x.wav")
    binary = tmp_path / "whisper-cli"
    binary.write_text("#!/bin/sh\n")
    settings.EVAC_WHISPER_BINARY = str(binary)
    settings.EVAC_WHISPER_MODEL = str(tmp_path / "model.bin")
    assert "No Whisper model" in whisper.status()[1]


# ------------------------------------------------------------------ 4.3 outbound
def raise_state(event, state, user, run, *, drill=False):
    from apps.evacuation.tests.conftest import tf

    with run():
        evac.change(event, state, actor=user, request=tf(user), drill=drill, source="web")


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


def test_evacuation_rings_handsets(acknowledged, link, dial, admin, run):
    raise_state(acknowledged, "evacuate", admin, run)
    b = Broadcast.objects.get()
    assert b.source == "evacuation" and b.kind == "emergency" and b.status == "sent" and b.text == "Evacuate"
    assert b.targets == 12 and "text message sent" in b.detail
    post = [c for c in dial.calls if c[1] == "emergency/broadcast/"][0]
    assert post[3] == {"event": "camp", "announcement": "Evacuate"}
    # staff alert is not in the default stages; the all clear follows a rung alarm
    raise_state(acknowledged, "all_clear", admin, run)
    assert Broadcast.objects.count() == 2 and Broadcast.objects.first().text == "All clear"
    raise_state(acknowledged, "staff_alert", admin, run)
    raise_state(acknowledged, "all_clear", admin, run)
    assert Broadcast.objects.count() == 2


def test_evacuation_broadcast_text_drill_and_group(acknowledged, link, dial, admin, run):
    from apps.evacuation.models import StageContent

    StageContent.objects.create(event=acknowledged, state="attention", speech_text="Please listen to staff.")
    raise_state(acknowledged, "attention", admin, run, drill=True)
    assert not Broadcast.objects.exists()  # drills ring only when allowed
    resave(link, {**link.settings, "broadcast_drills": True, "broadcast_group": "orga"}, {})
    raise_state(acknowledged, "shelter_in_place", admin, run, drill=True)
    assert outbound.stage_text(acknowledged, "attention", drill=True, zone_name="North") == \
        "DRILL: North: Please listen to staff."
    b = Broadcast.objects.get()
    assert b.text == "DRILL: Shelter in place" and b.group == "orga"
    assert [c for c in dial.calls if c[1] == "emergency/broadcast/"][0][3]["group"] == "orga"


def test_evacuation_broadcast_switched_off(acknowledged, link, dial, admin, run):
    resave(link, link.settings, {"evacuation_broadcast": False})
    raise_state(acknowledged, "evacuate", admin, run)
    assert not Broadcast.objects.exists()
    outbound.sink("other.type", {}, acknowledged)
    with mock.patch.object(outbound, "on_evacuation", side_effect=RuntimeError):
        outbound.sink("evacuation.state_changed", {}, acknowledged)  # never breaks the change


def test_broadcast_retries_then_fails(link, dial, django_capture_on_commit_callbacks):
    from apps.core.models import OutboxJob

    dial.routes[("POST", "emergency/broadcast/")] = (503, None)
    with django_capture_on_commit_callbacks(execute=True):
        b = outbound.queue(link, kind="emergency", source="test", text="Hello")
    b.refresh_from_db()
    job = OutboxJob.objects.get(kind="dial.broadcast")
    assert b.status == "pending" and b.attempts == 1 and "HTTP 503" in b.detail and job.status == "failed"
    dial.routes[("POST", "emergency/broadcast/")] = (404, {"detail": "emergency disabled"})
    outbound.handle_job(job)
    b.refresh_from_db()
    assert b.status == "failed" and "emergency disabled" in b.detail
    assert outbound.queue(link, kind="emergency", source="test", text="  ") is None
    assert outbound.queue(link, kind="message", source="test", text="x" * 600, reference="r").text == "x" * 480
    assert outbound.queue(link, kind="message", source="test", text="y", reference="r").text == "x" * 480


@pytest.fixture
def levels(event):
    ann_services.ensure_defaults(event)
    return {lv.key: lv for lv in Level.objects.filter(event=event)}


def test_announcement_channels(admin, event, levels, link, dial, django_capture_on_commit_callbacks):
    from apps.evacuation.tests.conftest import tf

    assert {"dial_call", "dial_sms"} <= set(ann_services.available_channels(event))
    a = Announcement(event=event, level=levels["info"], title="Dinner", body="Dinner is served.",
                     channels=["dial_call", "dial_sms"], channel_texts={"dial_sms": "Dinner now"})
    ann_services.save_draft(a, actor=admin)
    with django_capture_on_commit_callbacks(execute=True):
        ann_services.submit(a, actor=admin, request=tf(admin))
    report = {d.channel: d for d in a.deliveries.all()}
    assert report["dial_call"].status == Delivery.Status.SENT and report["dial_call"].recipients == 12
    assert report["dial_sms"].status == Delivery.Status.SENT and "5 sent, 1 failed" in report["dial_sms"].detail
    sms = [c for c in dial.calls if c[1] == "messaging/broadcast/"][0]
    assert sms[3] == {"event": "camp", "text": "Dinner now"}
    assert Broadcast.objects.filter(source="announcement").count() == 2
    resave(link, link.settings, {"announcements": False})
    assert "dial_call" not in ann_services.available_channels(event)
    d = report["dial_call"]
    assert outbound.channel("emergency")(d)["status"] == "skipped"


def test_test_broadcast_view(client, admin, event, link, dial, django_capture_on_commit_callbacks):
    tf_client(client, admin)
    with django_capture_on_commit_callbacks(execute=True):
        r = client.post(f"/e/{event.slug}/dial/test-broadcast/", {"kind": "message", "text": "Test"})
    assert r.status_code == 302 and Broadcast.objects.get().status == "sent"
    r = client.post(f"/e/{event.slug}/dial/test-broadcast/", {"kind": "nope", "text": ""})
    assert r.status_code == 302 and Broadcast.objects.count() == 1


# ------------------------------------------------------------------ 4.4 data sources + widgets
def test_data_sources(event, link, dial):
    book = sources.phonebook(event)
    assert book["count"] == 2 and book["items"][0] == {"number": "4300", "label": "4300", "name": "Medics",
                                                       "type": "Call group", "description": "First aid",
                                                       "location": "Tent 3", "category": ""}
    resave(link, {**link.settings, "important_numbers": "1100 = Info desk\nbad line\n112=x"}, {})
    nums = sources.numbers(event)["items"]
    assert nums[0] == {"number": "1100", "label": "Info desk", "kind": "important", "call": "Call 1100"}
    assert {"number": "112", "label": "x", "kind": "important", "call": "Call 112"} in nums  # own entry wins
    assert any(n["number"] == "110" and n["label"] == "Medics" for n in nums)  # named after the extension rung
    assert any(n["number"] == "9999" and n["label"] == "Voicemail" for n in nums)
    pages = sources.pages(event)
    assert pages["count"] == 1 and pages["items"][0]["markdown"] == "**SSID** camp"
    dect = sources.dect(event)
    assert dect["rfps"] == 2 and not dect["ok"] and dect["items"][0]["name"] == "RFP-2"
    assert dect["clusters"] == [{"name": "Main", "health": "degraded"}]
    assert [c for c in dial.calls if c[1] == "dect/rfps/"][0][2]["event__slug"] == "camp"


def test_data_sources_errors(event, link, dial):
    from apps.widgets.fetch import FetchError

    dial.routes[("GET", "emergency/targets/")] = (403, {"detail": "no scope"})
    assert sources.numbers(event)["count"] >= 2  # works without emergency:read
    dial.routes[("GET", "phonebook/")] = (500, None)
    with pytest.raises(FetchError):
        sources.phonebook(event)
    resave(link, link.settings, {"data_sources": False})
    with pytest.raises(FetchError):
        sources.pages(event)


def test_plain_text_from_html():
    assert sources.plain("<h1>T</h1><p>a<br>b &lt;x&gt;</p><script>x</script>") == "T\na\nb <x>\nx"


def test_install_widgets(client, admin, event, link, dial):
    modules.set_event(event, "widgets", True)
    tf_client(client, admin)
    r = client.post(f"/e/{event.slug}/dial/widgets/")
    assert r.status_code == 302
    assert CustomWidget.objects.filter(event=event, name__startswith="DIAL").count() == 5
    assert Feed.objects.filter(event=event, kind="source", source__startswith="dial.").count() == 4
    assert Feed.objects.get(source="dial.numbers").status == "ok"
    client.post(f"/e/{event.slug}/dial/widgets/")
    assert CustomWidget.objects.filter(event=event).count() == 5
    from apps.widgets import mapping

    w = CustomWidget.objects.get(name="DIAL: call X for Y")
    rows = mapping.rows(w.feed.snapshot, w.items_path, w.fields)
    assert rows[0] == {"title": "Call 112", "subtitle": "Medics"}


def test_status_page_snapshot(client, admin, event, link, dial, django_capture_on_commit_callbacks):
    tf_client(client, admin)
    with django_capture_on_commit_callbacks(execute=True):
        client.get(f"/e/{event.slug}/dial/")
    page = client.get(f"/e/{event.slug}/dial/")
    assert b"1 of 2 base stations up" in page.content and b"RFP-2" in page.content
    dial.routes[("GET", "dect/rfps/")] = (500, None)
    sources.take_snapshot(link, "dect")
    assert "HTTP 500" in Snapshot.objects.get(key="dect").error


# ------------------------------------------------------------------ 4.5 roles
def test_role_mapping_and_assign(client, admin, event, user, other, link, dial, role,
                                 django_capture_on_commit_callbacks):
    event_services.ensure_member(event, user)
    event_services.ensure_member(event, other)
    tf_client(client, admin)
    with django_capture_on_commit_callbacks(execute=True):
        page = client.get(f"/e/{event.slug}/dial/roles/")
    assert page.status_code == 200
    r = client.post(f"/e/{event.slug}/dial/roles/", {"what": "mapping", "role_orga": str(role("orga").pk),
                                                     "role_admin": str(role("viewer").pk), "role_user": ""})
    assert r.status_code == 302 and RoleMapping.objects.count() == 2
    rows = roles.proposals(link, Snapshot.objects.get(key="members").data["items"])
    by = {p["dial_user"]: p for p in rows}
    assert set(by) == {"alice", "bob"}  # zed's role "user" is not mapped
    assert by["alice"]["user"] == user and by["bob"]["user"] == other and not by["alice"]["has"]
    page = client.get(f"/e/{event.slug}/dial/roles/")
    assert b"alice" in page.content
    i = by["alice"]["index"]
    r = client.post(f"/e/{event.slug}/dial/roles/", {"what": "assign", f"pick_{i}": "on", f"user_{i}": str(user.pk),
                                                     f"pick_{by['bob']['index']}": "on",
                                                     f"user_{by['bob']['index']}": "not-a-member"})
    assert r.status_code == 302
    from apps.events.models import RoleAssignment

    assert RoleAssignment.objects.filter(membership__user=user, role=role("orga")).exists()
    assert not RoleAssignment.objects.filter(membership__user=other, role=role("viewer")).exists()
    assert roles.proposals(link, [{"user": "alice", "role": "orga"}])[0]["has"]


def test_roles_need_permission(client, member, event, link):
    tf_client(client, member)
    assert client.get(f"/e/{event.slug}/dial/roles/").status_code == 403
    assert client.get(f"/e/{event.slug}/dial/").status_code == 403


# ------------------------------------------------------------------ module off, a11y
def test_extensions_module_off(client, admin, event, link):
    modules.set_event(event, "extensions", False)
    tf_client(client, admin)
    assert client.get(f"/e/{event.slug}/dial/").status_code == 404


def test_pages_accessible(client, admin, event, link, dial, django_capture_on_commit_callbacks):
    tf_client(client, admin)
    with django_capture_on_commit_callbacks(execute=True):
        client.get(f"/e/{event.slug}/dial/")
        client.get(f"/e/{event.slug}/dial/roles/")
    for url in (f"/e/{event.slug}/dial/", f"/e/{event.slug}/dial/roles/"):
        assert audit_url(client, url) == [], url
    assert json.dumps(link.settings)


def test_emergency_level_recording_never_published_at_once(event, levels, link, speech_dir):
    lv = levels["emergency"]
    a = Announcement(event=event, level=lv, title="Phone", body="x", channels=["screens"])
    ann_services.submit_external(a, source="test", publish_now=True)
    assert a.status == Announcement.Status.PENDING
