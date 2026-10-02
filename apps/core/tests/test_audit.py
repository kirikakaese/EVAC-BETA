# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.db import connection
from django.test import RequestFactory

from apps.core.audit import export_csv, export_rows, log, verify_chain
from apps.core.models import AuditChainHead, AuditLog, ImmutableError


@pytest.mark.django_db
def test_log_appends_to_chain(user, event):
    a = log(action="test.one", actor=user, target=event, message="first")
    b = log(action="test.two", message="second", changes={"x": [1, 2]})
    assert b.prev_hash == a.hash
    assert a.event_id == event.pk and a.target_type == "events.event"
    assert AuditChainHead.objects.get(pk=1).last_hash == b.hash
    assert verify_chain().ok


@pytest.mark.django_db
def test_rows_are_immutable(user):
    a = log(action="test.one", actor=user)
    a.message = "changed"
    with pytest.raises(ImmutableError):
        a.save()
    with pytest.raises(ImmutableError):
        a.delete()
    with pytest.raises(ImmutableError):
        AuditLog.objects.filter(pk=a.pk).update(message="x")
    with pytest.raises(ImmutableError):
        AuditLog.objects.all().delete()


@pytest.mark.django_db
def test_tampering_via_sql_is_detected(user):
    log(action="test.one", actor=user)
    b = log(action="test.two", actor=user)
    log(action="test.three", actor=user)
    with connection.cursor() as cur:
        cur.execute("UPDATE core_auditlog SET message = 'forged' WHERE id = %s", [b.pk])
    result = verify_chain()
    assert not result.ok and result.first_bad_id == b.pk


@pytest.mark.django_db
def test_truncated_tail_is_detected(user):
    log(action="test.one", actor=user)
    last = log(action="test.two", actor=user)
    with connection.cursor() as cur:
        cur.execute("DELETE FROM core_auditlog WHERE id = %s", [last.pk])
    result = verify_chain()
    assert not result.ok and "head" in result.reason


@pytest.mark.django_db
def test_ip_and_request_actor(user):
    req = RequestFactory().post("/", REMOTE_ADDR="10.0.0.7")
    req.user = user
    entry = log(action="test.req", request=req)
    assert entry.ip_address == "10.0.0.7" and entry.actor_id == user.pk
    req.META["REMOTE_ADDR"] = "not-an-ip"
    assert log(action="test.req", request=req).ip_address is None
    assert verify_chain().ok


@pytest.mark.django_db
def test_exports(user):
    log(action="test.one", actor=user, changes={"a": [1, 2]})
    rows = export_rows(AuditLog.objects.all())
    assert rows[0]["action"] == "test.one"
    assert "test.one" in export_csv(AuditLog.objects.all())
