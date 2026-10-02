# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.core import crypto, outbox
from apps.core.models import OutboxJob
from apps.core.registry import registry
from apps.core.tasks import deliver_job, drain_outbox, purge_delivered_outbox


def test_encrypt_roundtrip_and_rotation():
    tok = crypto.encrypt("s3cret")
    assert tok != "s3cret" and crypto.decrypt(tok) == "s3cret"
    assert crypto.encrypt("") == "" and crypto.decrypt("") == ""
    assert crypto.decrypt_json(crypto.encrypt_json({"a": 1})) == {"a": 1}
    assert crypto.decrypt_json("") == {}
    new = crypto.generate_key()
    old_keys = list(__import__("django.conf").conf.settings.EVAC_SECRETS_KEYS)
    with override_settings(EVAC_SECRETS_KEYS=[new, *old_keys]):
        rotated = crypto.rotate(tok)
        assert crypto.decrypt(rotated) == "s3cret"
    with override_settings(EVAC_SECRETS_KEYS=[new]), pytest.raises(crypto.SecretError):
        crypto.decrypt(tok)
    with pytest.raises(crypto.SecretError):
        crypto.decrypt_json(crypto.encrypt("[1]"))


def test_dev_key_derived_from_secret_key():
    with override_settings(EVAC_SECRETS_KEYS=[]):
        assert crypto.decrypt(crypto.encrypt("x")) == "x"


@pytest.fixture
def handler(monkeypatch):
    calls = []

    def ok(job):
        calls.append(job.payload)
        job.result = {"fine": True}

    def fail(job):
        raise RuntimeError("boom")

    monkeypatch.setitem(registry.outbox_handlers, "test.ok", ok)
    monkeypatch.setitem(registry.outbox_handlers, "test.fail", fail)
    return calls


@pytest.mark.django_db(transaction=True)
def test_enqueue_delivers_on_commit(handler):
    job = outbox.enqueue("test.ok", {"n": 1}, key="k1")
    job.refresh_from_db()
    assert job.status == OutboxJob.Status.DONE and handler == [{"n": 1}] and job.result == {"fine": True}
    assert outbox.enqueue("test.ok", {"n": 2}, key="k1").pk == job.pk  # idempotent
    assert len(handler) == 1


@pytest.mark.django_db
def test_failure_backoff_and_dead_letter(handler, settings):
    settings.EVAC_OUTBOX_MAX_ATTEMPTS = 2
    job = outbox.enqueue("test.fail", {}, deliver_now=False)
    assert outbox.depth() == 1
    assert deliver_job(str(job.pk)) is False
    job.refresh_from_db()
    assert job.status == OutboxJob.Status.FAILED and job.attempts == 1 and "boom" in job.last_error
    assert job.next_attempt_at > timezone.now()
    assert drain_outbox() == 0  # not due yet
    OutboxJob.objects.filter(pk=job.pk).update(next_attempt_at=timezone.now())
    drain_outbox()
    job.refresh_from_db()
    assert job.status == OutboxJob.Status.DEAD and outbox.depth() == 0


@pytest.mark.django_db
def test_missing_handler_and_purge(handler):
    job = outbox.enqueue("test.unknown", {}, deliver_now=False)
    drain_outbox()
    job.refresh_from_db()
    assert job.status == OutboxJob.Status.DEAD
    ok = outbox.enqueue("test.ok", {}, deliver_now=False)
    assert drain_outbox() == 1
    OutboxJob.objects.filter(pk=ok.pk).update(delivered_at=timezone.now() - dt.timedelta(days=30))
    assert purge_delivered_outbox() == 1
    assert outbox.backoff(1) == dt.timedelta(seconds=10)
