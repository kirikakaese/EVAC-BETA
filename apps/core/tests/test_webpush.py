# SPDX-License-Identifier: AGPL-3.0-or-later
import base64
import json
import os
import struct
from unittest import mock

import pytest
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF, HKDFExpand

from apps.core import outbox, webpush
from apps.core.models import Notification, OutboxJob, PushSubscription, VapidKey
from apps.core.notify import notify


class Browser:
    """The receiving side of RFC 8291 (what a browser does), to check our encryption end to end."""

    def __init__(self):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        pub = self.key.public_key().public_bytes(serialization.Encoding.X962,
                                                 serialization.PublicFormat.UncompressedPoint)
        self.p256dh = webpush.b64u(pub)
        self.pub = pub

    def subscription(self, endpoint="https://push.example.org/send/abc"):
        return {"endpoint": endpoint, "keys": {"p256dh": self.p256dh, "auth": webpush.b64u(self.auth)}}

    def decrypt(self, body: bytes) -> bytes:
        salt, rs, idlen = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
        as_public = body[21:21 + idlen]
        assert rs == 4096 and idlen == 65
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
        ikm = HKDF(hashes.SHA256(), 32, salt=self.auth, info=b"WebPush: info\x00" + self.pub + as_public).derive(shared)
        prk = webpush._extract(salt, ikm)
        cek = HKDFExpand(hashes.SHA256(), 16, info=b"Content-Encoding: aes128gcm\x00").derive(prk)
        nonce = HKDFExpand(hashes.SHA256(), 12, info=b"Content-Encoding: nonce\x00").derive(prk)
        plain = AESGCM(cek).decrypt(nonce, body[21 + idlen:], None)
        assert plain.endswith(b"\x02")
        return plain[:-1]


def test_encrypt_roundtrip():
    b = Browser()
    payload = json.dumps({"title": "Storm", "body": "Leave the field ✓"}).encode()
    assert b.decrypt(webpush.encrypt(payload, b.p256dh, webpush.b64u(b.auth))) == payload
    with pytest.raises(ValueError):
        webpush.encrypt(b"x" * 5000, b.p256dh, webpush.b64u(b.auth))


def test_rfc8291_test_vector():
    """RFC 8291, section 5 (fixed keys and salt give the published ciphertext)."""
    def d(s):
        return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

    as_private = ec.derive_private_key(int.from_bytes(d("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
                                       ec.SECP256R1())
    body = webpush.encrypt(b"When I grow up, I want to be a watermelon",
                           "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                           "BTBZMqHH6r4Tts7J_aSIgg", salt=d("DGv6ra1nlYgDCS1FRnbzlw"), server_key=as_private)
    assert webpush.b64u(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3"
        "jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def test_vapid_key_is_created_once_and_signs(db, settings):
    settings.EVAC_VAPID_SUBJECT = "mailto:ops@example.org"
    key = webpush.public_key()
    assert webpush.public_key() == key and VapidKey.objects.count() == 1
    assert "PRIVATE" not in VapidKey.objects.get().private_key_encrypted
    header = webpush.vapid_header("https://fcm.googleapis.com/fcm/send/xyz", now=1_000_000)
    token, k = header.removeprefix("vapid t=").split(", k=")
    assert k == key
    h, c, sig = token.split(".")
    claims = json.loads(webpush.b64u_decode(c))
    assert claims == {"aud": "https://fcm.googleapis.com", "exp": 1_000_000 + 43200, "sub": "mailto:ops@example.org"}
    assert json.loads(webpush.b64u_decode(h)) == {"typ": "JWT", "alg": "ES256"}
    raw = webpush.b64u_decode(sig)
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.b64u_decode(key))
    public.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
                  f"{h}.{c}".encode(), ec.ECDSA(hashes.SHA256()))


def test_subscribe_validates_and_moves(user, other):
    b = Browser()
    sub = webpush.subscribe(user, b.subscription(), "Firefox")
    assert sub.user == user and sub.user_agent == "Firefox"
    # the same browser signs in as someone else: the subscription moves
    assert webpush.subscribe(other, b.subscription()).pk == sub.pk
    assert PushSubscription.objects.get().user == other
    for bad in [{"endpoint": "http://x.example.org", "keys": b.subscription()["keys"]},
                {"endpoint": "https://x.example.org", "keys": {"p256dh": "abc", "auth": "def"}},
                {"endpoint": "https://x.example.org", "keys": {"p256dh": webpush.b64u(b"\x04" + b"\x00" * 64),
                                                              "auth": webpush.b64u(b"1" * 16)}}]:
        with pytest.raises(ValueError):
            webpush.subscribe(user, bad)


class Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


@pytest.fixture
def run(django_capture_on_commit_callbacks):
    def call(fn, *args, **kwargs):
        with django_capture_on_commit_callbacks(execute=True):
            return fn(*args, **kwargs)
    return call


def test_notify_pushes_to_every_device(user, event, run):
    b1, b2 = Browser(), Browser()
    webpush.subscribe(user, b1.subscription("https://push.example.org/1"))
    webpush.subscribe(user, b2.subscription("https://push.example.org/2"))
    sent = []

    def post(url, data=None, headers=None, timeout=None):
        sent.append((url, data, headers))
        return Resp(201)

    with mock.patch("apps.core.webpush.requests.post", side_effect=post):
        run(notify, [user], "Emergency: Storm", body="Leave the field", url="/e/demo/", level="err", event=event)
    assert len(sent) == 2
    url, body, headers = sent[0]
    browser = b1 if url.endswith("/1") else b2
    msg = json.loads(browser.decrypt(body))
    n = Notification.objects.get()
    assert msg == {"title": "Emergency: Storm", "body": "Leave the field", "url": "/e/demo/", "level": "err",
                   "tag": f"evac-{n.pk}", "event": "demo"}
    assert headers["Urgency"] == "high" and headers["TTL"] == "600" and headers["Content-Encoding"] == "aes128gcm"
    assert headers["Authorization"].startswith("vapid t=")
    assert all(s.last_success_at for s in PushSubscription.objects.all())


def test_gone_refused_and_retry(user, run):
    webpush.subscribe(user, Browser().subscription())
    with mock.patch("apps.core.webpush.requests.post", return_value=Resp(410)):
        run(notify, [user], "Hi")
    assert not PushSubscription.objects.exists()
    assert OutboxJob.objects.get().result == {"removed": "the push service no longer knows this browser"}

    OutboxJob.objects.all().delete()
    webpush.subscribe(user, Browser().subscription())
    with mock.patch("apps.core.webpush.requests.post", return_value=Resp(400, "bad payload")):
        run(notify, [user], "Hi")
    assert PushSubscription.objects.get().failures == 1
    assert "refused" in OutboxJob.objects.get().result

    OutboxJob.objects.all().delete()
    with mock.patch("apps.core.webpush.requests.post", return_value=Resp(503)):
        run(notify, [user], "Hi")
    job = OutboxJob.objects.get()
    assert job.status == "failed" and "503" in job.last_error
    with mock.patch("apps.core.webpush.requests.post", side_effect=requests.Timeout("https://push.example.org/x")):
        outbox.deliver(job)
    assert "push.example.org" not in job.last_error
    with mock.patch("apps.core.webpush.requests.post", return_value=Resp(201)):
        assert outbox.deliver(job)


def test_job_for_deleted_rows_is_skipped(user):
    job = OutboxJob(kind=webpush.JOB_KIND, payload={"subscription": 999, "notification": 999})
    webpush.handle_job(job)
    assert job.result == {"skipped": "subscription or notification gone"}


def test_no_devices_no_jobs(user, run):
    run(notify, [user], "Hi")
    assert not OutboxJob.objects.filter(kind=webpush.JOB_KIND).exists()


def test_push_endpoints(client, user):
    client.force_login(user)
    b = Browser()
    r = client.post("/push/subscribe/", data=json.dumps(b.subscription()), content_type="application/json",
                    HTTP_USER_AGENT="Pixel")
    assert r.json() == {"ok": True} and PushSubscription.objects.get().user_agent == "Pixel"
    assert client.post("/push/subscribe/", data="[]", content_type="application/json").status_code == 400
    assert client.post("/push/subscribe/", data="nope", content_type="application/json").status_code == 400
    with mock.patch("apps.core.webpush.requests.post", return_value=Resp(201)):
        r = client.post("/push/test/", {"next": "/e/demo/staff/"})
    assert r.status_code == 302 and r["Location"] == "/e/demo/staff/"
    assert Notification.objects.filter(user=user, title="Test notification").exists()
    r = client.post("/push/unsubscribe/", data=json.dumps({"endpoint": b.subscription()["endpoint"]}),
                    content_type="application/json")
    assert r.json() == {"ok": True, "deleted": 1}
    assert client.post("/push/unsubscribe/", data="x", content_type="application/json").json()["deleted"] == 0
    r = client.post("/push/test/", {"next": "https://evil.example.org/"})
    assert r["Location"] == "/notifications/"
    client.logout()
    assert client.post("/push/subscribe/", data="{}", content_type="application/json").status_code == 302
