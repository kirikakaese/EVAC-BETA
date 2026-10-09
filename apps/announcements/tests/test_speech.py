# SPDX-License-Identifier: AGPL-3.0-or-later
import io
import json
import os
import shutil
import stat
import sys
import tarfile
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.announcements import services, tts
from apps.announcements.models import Announcement, Level
from apps.core import settings_store
from conftest import login_2fa

FAKE_PIPER = f"""#!{sys.executable}
# stands in for Piper: --model M --output_file F, text on stdin -> a short WAV
import sys, wave
args = sys.argv[1:]
model, out = args[args.index("--model") + 1], args[args.index("--output_file") + 1]
text = sys.stdin.read()
if "FAIL" in text:
    print("boom: cannot speak", file=sys.stderr); sys.exit(3)
with open(out + ".log", "a") as log:
    log.write(model + "|" + text + "\\n")
with wave.open(out, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b"\\x00\\x01" * 8000)
"""


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    return tmp_path


@pytest.fixture
def piper(media, settings):
    path = media / "piper"
    path.write_text(FAKE_PIPER)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    settings.EVAC_PIPER_BINARY = str(path)
    return path


def add_voice(name="en_GB-test-medium"):
    d = tts.voices_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.onnx").write_bytes(b"model")
    (d / f"{name}.onnx.json").write_text(json.dumps({"language": {"code": "en_GB"}, "audio": {"quality": "medium",
                                                                                         "sample_rate": 22050}}))
    return d / f"{name}.onnx"


@pytest.fixture
def voice(piper):
    return add_voice()


@pytest.fixture
def levels(event):
    services.ensure_defaults(event)
    return {lv.key: lv for lv in Level.objects.filter(event=event)}


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    def call(fn, *args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return fn(*args, **kwargs)
    return call


def tf(user):
    from django.test import RequestFactory

    from apps.accounts.twofactor import SESSION_KEY

    request = RequestFactory().get("/")
    request.user, request.session = user, {SESSION_KEY: "x"}
    return request


def publish(admin, event, level, run, **kw):
    a = Announcement(event=event, level=level, title=kw.pop("title", "Lost child"),
                     body=kw.pop("body", "Mia, six years, red jacket."), channels=kw.pop("channels", ["screens"]), **kw)
    services.save_draft(a, actor=admin)
    run(services.submit, a, actor=admin, request=tf(admin))
    a.refresh_from_db()
    return a


# ------------------------------------------------------------------ tts module
def test_status_and_voice_choice(media, settings):
    settings.EVAC_PIPER_BINARY = str(media / "missing")
    with mock.patch("apps.announcements.tts.shutil.which", return_value=None):
        assert tts.status() == (False, "Piper is not installed on the server.")
    settings.EVAC_PIPER_BINARY = sys.executable  # any existing file counts as the binary
    assert not tts.status()[0] and "No voice installed" in tts.status()[1]
    add_voice("de_DE-x-low")
    assert tts.choose_voice()[0] == "de_DE-x-low"
    add_voice("en_US-amy-low")
    assert tts.choose_voice()[0] == "en_US-amy-low"  # English first
    assert tts.choose_voice("de_DE-x-low")[0] == "de_DE-x-low"
    assert tts.status() == (True, "Voice en_US-amy-low.")
    assert tts.voice_info(tts.voices()["en_US-amy-low"])["language"] == "en_GB"
    (tts.voices_dir() / "broken.onnx").write_bytes(b"")  # no .json: not a voice
    assert "broken" not in tts.voices()
    assert tts.voice_info(tts.voices_dir() / "broken.onnx") == {}


def test_render_caches_and_converts(voice, piper):
    name = tts.render("Doors open in ten minutes.")
    assert name.endswith(".m4a" if shutil.which("ffmpeg") else ".wav")
    assert tts.path_of(name).stat().st_size > 100
    assert tts.render("Doors open in ten minutes.") == name  # cached: same voice and text
    assert not list(tts.speech_dir().rglob("*.log"))  # Piper ran in a temporary directory
    with mock.patch("apps.announcements.tts.shutil.which", return_value=None):
        wav = tts.render("Without ffmpeg.")
    assert wav.endswith(".wav")
    with pytest.raises(tts.SpeechError, match="boom"):
        tts.render("FAIL please")
    with mock.patch("apps.announcements.tts.subprocess.run", side_effect=OSError("exec")):
        with pytest.raises(tts.SpeechError, match="did not run"):
            tts.render("another text")


def test_render_without_piper(media, settings):
    settings.EVAC_PIPER_BINARY = str(media / "missing")
    with mock.patch("apps.announcements.tts.shutil.which", return_value=None):
        with pytest.raises(tts.SpeechError, match="not installed"):
            tts.render("x")


# ------------------------------------------------------------------ announcements
def test_spoken_text():
    lv = Level(name="Urgent")
    a = Announcement(level=lv, title="Lost child.", body="Mia, six years.")
    assert services.speech_text(a) == "Urgent. Lost child. Mia, six years."
    a.body = a.title
    assert services.speech_text(a) == "Urgent. Lost child."
    a.channel_texts = {"speech": "  Attention please.  "}
    assert services.speech_text(a) == "Attention please."


def test_speech_text_validation(admin, event, levels):
    a = Announcement(event=event, level=levels["urgent"], title="x", channels=["screens"],
                     channel_texts={"speech": "y" * 1001})
    with pytest.raises(ValidationError, match="spoken text is too long"):
        services.save_draft(a, actor=admin)
    a.channel_texts = {"speech": "fine"}
    services.save_draft(a, actor=admin)


def test_speech_rendered_on_approval_and_in_program(admin, event, levels, voice, run, client):
    a = publish(admin, event, levels["urgent"], run)
    assert a.speech_status == "ready" and a.speech_file.endswith((".m4a", ".wav"))
    assert a.speech_file.startswith(tts.key_for("en_GB-test-medium", "Urgent. Lost child. Mia, six years, red jacket."))
    # the screen program carries a signed URL; the player fetches it without a token
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    from apps.screens import services as screen_services

    screen = screen_services.pair(event, data["code"], actor=admin, name="Foyer")
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    program = client.get("/player/api/playlists/program/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["program"]
    url = program["overlays"][0]["speech"]
    assert url.startswith(f"/player/api/announcements/speech/{a.speech_file}?s={screen.pk}.")
    r = client.get(url)
    assert r.status_code == 200 and r["Content-Type"] in ("audio/mp4", "audio/wav")
    assert "immutable" in r["Cache-Control"]
    assert client.get(url.split("?")[0]).status_code == 401
    assert client.get(url.split("?")[0], HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200
    assert client.get(url[:-3] + "xyz").status_code == 401  # bad signature
    other = "0" * 64 + ".m4a"
    assert client.get(f"/player/api/announcements/speech/{other}",
                      HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 404
    # emergency takeovers carry it on the entry
    e = publish(admin, event, levels["emergency"], run, title="Storm", body="Leave the field.")
    program = client.get("/player/api/playlists/program/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["program"]
    entry = next(x for x in program["entries"] if x["id"] == f"announcement:{e.pk}")
    assert entry["speech"].startswith("/player/api/announcements/speech/")
    # the portal preview
    login_2fa(client, admin)
    assert client.get(f"/e/demo/announcements/{a.pk}/speech/").status_code == 200
    page = client.get(f"/e/demo/announcements/{a.pk}/").content.decode()
    assert "Spoken on screens" in page and "<audio" in page


def test_levels_that_do_not_speak_and_missing_voice(admin, event, levels, run, media, settings):
    a = publish(admin, event, levels["info"], run)
    assert a.speech_status == ""  # info is not read aloud
    b = publish(admin, event, levels["urgent"], run, channels=["staff"])
    assert b.speech_status == ""  # not on screens
    settings.EVAC_PIPER_BINARY = str(media / "missing")
    with mock.patch("apps.announcements.tts.shutil.which", return_value=None):
        c = publish(admin, event, levels["urgent"], run)
    assert c.speech_status == "unavailable" and "not installed" in c.speech_detail
    assert services.speech_url(c) == ""


def test_failed_render_and_render_again(admin, event, levels, voice, run, client):
    a = publish(admin, event, levels["urgent"], run, title="FAIL")
    assert a.speech_status == "failed" and "boom" in a.speech_detail
    a.title = "Better"
    a.save()
    login_2fa(client, admin)
    with_capture = run(client.post, f"/e/demo/announcements/{a.pk}/speech/render/")
    assert with_capture.status_code == 302
    a.refresh_from_db()
    assert a.speech_status == "ready"
    assert client.get(f"/e/demo/announcements/{a.pk}/speech/").status_code == 200
    from apps.core.models import OutboxJob

    job = OutboxJob(payload={"announcement": "00000000-0000-0000-0000-000000000000"})
    services.render_speech(job)
    assert job.result == {"skipped": "announcement gone"}


def test_render_again_needs_permission(client, event, levels, member, admin, voice, run):
    a = publish(admin, event, levels["urgent"], run)
    login_2fa(client, member)
    assert client.post(f"/e/demo/announcements/{a.pk}/speech/render/").status_code == 403
    Announcement.objects.filter(pk=a.pk).update(speech_status="pending")
    assert client.get(f"/e/demo/announcements/{a.pk}/speech/").status_code == 404


def test_composer_spoken_text_and_voice_setting(client, admin, event, levels, voice, run):
    add_voice("en_US-amy-low")
    settings_store.save("announcements", "event", str(event.pk), {"tts_voice": "en_US-amy-low"}, user=admin,
                        event=event)
    login_2fa(client, admin)
    page = client.get("/e/demo/announcements/new/")
    assert "text_speech" in page.context["form"].fields
    run(client.post, "/e/demo/announcements/new/", {
        "level": levels["urgent"].pk, "title": "Bar closes", "body": "", "short": "", "channels": ["screens"],
        "all_screens": "on", "text_speech": "The bar closes in ten minutes.", "action": "send"})
    a = Announcement.objects.get(title="Bar closes")
    assert a.channel_texts == {"speech": "The bar closes in ten minutes."} and a.speech_status == "ready"
    assert a.speech_file.startswith(tts.key_for("en_US-amy-low", "The bar closes in ten minutes."))


def test_level_form_speak(client, admin, event, levels):
    login_2fa(client, admin)
    lv = levels["info"]
    client.post(f"/e/demo/announcements/levels/{lv.pk}/", {
        "name": "Info", "rank": 10, "colour": "#2563eb", "display": "ticker", "sound": "none", "speak": "on",
        "min_display_seconds": 60, "repeat_every_minutes": 0, "default_channels": ["screens"]})
    lv.refresh_from_db()
    assert lv.speak
    assert levels["urgent"].speak and levels["emergency"].speak and not levels["important"].speak


# ------------------------------------------------------------------ evac_tts command
def test_command(voice, media, tmp_path):
    out = io.StringIO()
    call_command("evac_tts", "status", stdout=out)
    assert "ready: Voice en_GB-test-medium." in out.getvalue()
    out = io.StringIO()
    call_command("evac_tts", "list", stdout=out)
    assert "en_GB-test-medium  en_GB  medium" in out.getvalue()
    out = io.StringIO()
    call_command("evac_tts", "say", "Hello there", stdout=out)
    assert out.getvalue().strip().startswith(str(tts.speech_dir()))
    with pytest.raises(CommandError, match="boom"):
        call_command("evac_tts", "say", "FAIL")
    # install: a tar package (paths flattened) and a plain .onnx with its .json
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "en_US-new-low.onnx").write_bytes(b"m")
    (src / "en_US-new-low.onnx.json").write_text("{}")
    tar_path = tmp_path / "voice.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(src / "en_US-new-low.onnx", arcname="nested/dir/en_US-new-low.onnx")
        tar.add(src / "en_US-new-low.onnx.json", arcname="nested/dir/en_US-new-low.onnx.json")
    call_command("evac_tts", "install", str(tar_path), stdout=io.StringIO())
    assert "en_US-new-low" in tts.voices()
    (src / "en_GB-plain-low.onnx").write_bytes(b"m")
    (src / "en_GB-plain-low.onnx.json").write_text("{}")
    call_command("evac_tts", "install", str(src / "en_GB-plain-low.onnx"), stdout=io.StringIO())
    assert "en_GB-plain-low" in tts.voices()
    (src / "lonely.onnx").write_bytes(b"m")
    with pytest.raises(CommandError, match="missing"):
        call_command("evac_tts", "install", str(src / "lonely.onnx"))
    with pytest.raises(CommandError, match="no such file"):
        call_command("evac_tts", "install", str(tmp_path / "nope.onnx"))
    with pytest.raises(CommandError, match="expected"):
        call_command("evac_tts", "install", str(src / "en_GB-plain-low.onnx.json"))
    empty = tmp_path / "empty.tar.gz"
    with tarfile.open(empty, "w:gz"):
        pass
    with pytest.raises(CommandError, match="no voice"):
        call_command("evac_tts", "install", str(empty))


def test_command_without_voices(media, settings):
    settings.EVAC_PIPER_BINARY = str(media / "missing")
    out = io.StringIO()
    with mock.patch("apps.announcements.tts.shutil.which", return_value=None):
        call_command("evac_tts", "list", stdout=out)
        call_command("evac_tts", "status", stdout=out)
    assert "No voices" in out.getvalue() and "not ready" in out.getvalue()


@pytest.mark.skipif(not os.environ.get("EVAC_TEST_PIPER"), reason="set EVAC_TEST_PIPER=<piper> and install a voice")
def test_real_piper(settings):
    """Opt-in smoke test with a real Piper and voice (not run in CI)."""
    settings.EVAC_PIPER_BINARY = os.environ["EVAC_TEST_PIPER"]
    settings.EVAC_TTS_VOICES_DIR = os.environ.get("EVAC_TEST_VOICES", str(tts.voices_dir()))
    name = tts.render("Doors open in ten minutes.")
    assert tts.path_of(name).stat().st_size > 5_000
