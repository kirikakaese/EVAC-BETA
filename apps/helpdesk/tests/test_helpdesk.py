# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpdesk (ADR-0043): lost & found with matching, public forms (honeypot, rate limit), requests, FAQ."""
import datetime as dt
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils import timezone

from apps.core import modules, settings_store
from apps.core.a11y import check_html
from apps.helpdesk import panels, services
from apps.helpdesk.models import FaqEntry, LostFound, Ticket, TicketNote
from conftest import login_2fa

pytestmark = pytest.mark.django_db


def item(event, kind, what, **kw):
    return services.save_item(LostFound(event=event, kind=kind, what=what, **kw), actor=None)


def test_references_and_matching(event):
    lost = item(event, "lost", "Black backpack", category="bag", colour="black", description="laptop, blue bottle",
                when=timezone.now())
    other = item(event, "lost", "Keys", category="keys")
    found = item(event, "found", "Backpack with laptop", category="bag", colour="Black")
    jacket = item(event, "found", "Jacket", category="clothing", colour="black")
    assert (lost.reference, other.reference, found.reference) == ("L-0001", "L-0002", "F-0001")
    sugg = services.suggestions(lost)
    assert sugg[0][1] == found and all(o != jacket for _s, o in sugg)
    early = item(event, "found", "Backpack", category="bag", colour="black",
                 when=timezone.now() - dt.timedelta(days=1))
    assert services.score(lost, early) < services.score(lost, found)
    with pytest.raises(ValidationError):
        services.match(lost, other, actor=None)
    services.match(lost, found, actor=None)
    lost.refresh_from_db()
    assert lost.status == found.status == "matched" and lost.match == found
    assert services.suggestions(lost) == []
    with pytest.raises(ValidationError):
        services.match(lost, early, actor=None)
    services.unmatch(found, actor=None)
    lost.refresh_from_db()
    assert lost.status == "open" and lost.match is None
    with pytest.raises(ValidationError, match="Say what"):
        item(event, "found", " ")


def test_hand_over_and_close(event, admin):
    lost = item(event, "lost", "Glasses", category="glasses", name="Ana")
    found = item(event, "found", "Glasses", category="glasses")
    with pytest.raises(ValidationError, match="Match"):
        services.hand_over(lost, to="Ana", actor=admin)
    services.match(found, lost, actor=admin)
    found.refresh_from_db()
    services.hand_over(found, to="", actor=admin)  # the owner's name from the lost report
    lost.refresh_from_db()
    assert lost.status == "returned" and lost.handed_to == "Ana" and lost.handed_by == admin
    with pytest.raises(ValidationError, match="Already"):
        services.hand_over(found, to="Ana", actor=admin)
    stray = item(event, "found", "Umbrella")
    with pytest.raises(ValidationError, match="whom"):
        services.hand_over(stray, to="", actor=admin)
    services.close(stray, actor=admin, reason="donated")
    assert LostFound.objects.get(pk=stray.pk).status == "closed"


def test_public_page_forms_and_status(client, event, admin):
    FaqEntry.objects.create(event=event, question="Cloakroom?", answer="Foyer", topic="Venue")
    FaqEntry.objects.create(event=event, question="Internal?", answer="x", public=False)
    item(event, "found", "Red scarf", category="clothing", colour="red", description="SECRET-DETAIL", name="Finder",
         contact="0170 SECRET")
    page = client.get(f"/public/{event.slug}/help/").content.decode()
    assert "Cloakroom?" in page and "Internal?" not in page and "Red scarf" in page
    assert "SECRET" not in page and check_html(page) == []
    for what in ("request", "lost"):
        assert check_html(client.get(f"/public/{event.slug}/help/{what}/").content.decode()) == []
    assert client.get(f"/public/{event.slug}/help/other/").status_code == 404
    with mock.patch("apps.core.notify.notify") as notify:
        r = client.post(f"/public/{event.slug}/help/request/", {"category": "accessibility", "subject": "Ramp",
                                                                 "body": "Where is the ramp?", "contact": "a@b.c"})
    t = Ticket.objects.get()
    assert r.status_code == 302 and r.url.endswith(f"/status/{t.token}/") and t.source == "public"
    assert t.reference == "R-0001" and notify.called
    status = client.get(r.url)
    assert status["Cache-Control"] == "private, no-store" and b"R-0001" in status.content
    assert check_html(status.content.decode()) == []
    # honeypot: looks fine, stores nothing
    client.post(f"/public/{event.slug}/help/request/", {"category": "question", "subject": "Buy", "body": "spam",
                                                        "website": "http://spam.example"})
    assert Ticket.objects.count() == 1
    # lost report needs a contact
    client.post(f"/public/{event.slug}/help/lost/", {"what": "Phone", "category": "electronics"})
    assert not LostFound.objects.filter(kind="lost").exists()
    r = client.post(f"/public/{event.slug}/help/lost/", {"what": "Phone", "category": "electronics",
                                                          "contact": "0170"})
    lost = LostFound.objects.get(kind="lost")
    assert lost.source == "public" and b"looking" in client.get(r.url).content
    assert client.get(f"/public/{event.slug}/help/status/nope/").status_code == 404


@override_settings(EVAC_RATE_LIMITS={"public_form": 2})
def test_public_rate_limit_and_switches(client, event):
    url = f"/public/{event.slug}/help/request/"
    codes = [client.post(url, {"category": "question", "subject": "s", "body": "b"}).status_code for _ in range(3)]
    assert codes == [302, 302, 429]
    settings_store.save("helpdesk", "event", str(event.pk), {"public_lost": False, "public_found": False},
                        event=event)
    assert client.get(f"/public/{event.slug}/help/lost/").status_code == 404
    assert b"Found items" not in client.get(f"/public/{event.slug}/help/").content
    settings_store.save("helpdesk", "event", str(event.pk), {"public_page": False}, event=event)
    assert client.get(f"/public/{event.slug}/help/").status_code == 404
    settings_store.save("helpdesk", "event", str(event.pk), {"public_page": True}, event=event)
    modules.set_instance("helpdesk", False)
    assert client.get(f"/public/{event.slug}/help/").status_code == 404


def test_requests_update_notes_and_replies(client, event, admin, user, member):
    t = services.submit(Ticket(event=event, subject="Lockers", body="Big bag?", source="public"), actor=None)
    with pytest.raises(ValidationError):
        services.submit(Ticket(event=event, subject="", body=""), actor=None)
    services.update(t, assignee=user, actor=admin)
    t.refresh_from_db()
    assert t.status == "open" and t.assignee == user
    from apps.core.models import Notification
    assert Notification.objects.filter(user=user, title__startswith="Assigned").exists()
    services.update(t, note="internal", actor=admin)
    services.update(t, status="done", note="Lockers at gate B", public=True, actor=admin)
    assert list(TicketNote.objects.values_list("public", flat=True)) == [False, True]
    page = client.get(f"/public/{event.slug}/help/status/{t.token}/").content.decode()
    assert "Lockers at gate B" in page and "internal" not in page
    with pytest.raises(ValidationError):
        services.update(t, status="bogus", actor=admin)
    assert services.update(t, actor=admin) == t  # nothing to do


def test_staff_pages(client, event, admin):
    c = login_2fa(client, admin)
    t = services.submit(Ticket(event=event, subject="Toilet", body="blocked", category="problem"), actor=admin)
    lost = item(event, "lost", "Black backpack", category="bag", colour="black", name="Jonas", contact="0170")
    found = item(event, "found", "Backpack", category="bag", colour="black", storage="Box 1")
    base = f"/e/{event.slug}/helpdesk/"
    for url in ["", "?status=mine", "?status=done", "requests/new/", f"requests/{t.pk}/", "lost-found/",
                "lost-found/?kind=lost&status=all&q=back", "lost-found/new/", "lost-found/new/?kind=lost",
                f"lost-found/{found.pk}/", f"lost-found/{lost.pk}/", f"lost-found/{found.pk}/edit/", "faq/"]:
        r = c.get(base + url)
        assert r.status_code == 200, url
        assert check_html(r.content.decode()) == [], url
    assert b"score" in c.get(f"{base}lost-found/{lost.pk}/").content
    c.post(f"{base}lost-found/{lost.pk}/action/", {"action": "match", "other": str(found.pk)})
    assert LostFound.objects.get(pk=found.pk).status == "matched"
    assert check_html(c.get(f"{base}lost-found/{lost.pk}/").content.decode()) == []
    c.post(f"{base}lost-found/{lost.pk}/action/", {"action": "hand_over", "to": "Jonas"})
    assert LostFound.objects.get(pk=found.pk).handed_to == "Jonas"
    r = c.post(f"{base}lost-found/new/?kind=found", {"what": "Umbrella", "category": "other", "public": "on"})
    assert r.status_code == 302 and LostFound.objects.filter(what="Umbrella").exists()
    r = c.post(f"{base}requests/new/", {"category": "question", "subject": "Wifi", "body": "Password?"})
    assert r.status_code == 302
    c.post(f"{base}requests/{t.pk}/", {"u-status": "waiting", "u-note": "Plumber called"})
    assert Ticket.objects.get(pk=t.pk).status == "waiting"
    c.post(f"{base}faq/", {"question": "Wifi?", "answer": "evac / guest", "topic": "Venue", "order": 1,
                           "public": "on", "on_screens": "on"})
    e = FaqEntry.objects.get(question="Wifi?")
    c.post(f"{base}faq/{e.pk}/", {"delete": "1"})
    assert not FaqEntry.objects.exists()


def test_permissions(client, event, user, member):
    client.force_login(user)  # viewer: sees the queue, cannot act
    t = services.submit(Ticket(event=event, subject="x", body="y"), actor=None)
    assert client.get(f"/e/{event.slug}/helpdesk/").status_code == 200
    assert client.post(f"/e/{event.slug}/helpdesk/requests/{t.pk}/", {"u-status": "done"}).status_code == 403
    assert client.get(f"/e/{event.slug}/helpdesk/faq/").status_code == 403
    assert client.get(f"/e/{event.slug}/helpdesk/lost-found/new/").status_code == 403


def test_sources_panels_api_and_ops(client, event, admin):
    FaqEntry.objects.create(event=event, question="Q", answer="A", on_screens=True)
    FaqEntry.objects.create(event=event, question="Hidden", answer="A")
    item(event, "found", "Scarf", category="clothing", colour="red", contact="secret")
    item(event, "found", "Private", public=False)
    services.submit(Ticket(event=event, subject="Help", body="x", category="accessibility"), actor=None)
    assert [i["title"] for i in panels.faq_source(event)["items"]] == ["Q"]
    found = panels.found_source(event)["items"]
    assert [i["title"] for i in found] == ["Scarf"] and "secret" not in str(found) and "T" in found[0]["time"]
    assert panels.queue_source(event) == {"open": 1, "new": 1}
    c = login_2fa(client, admin)
    assert c.get(f"/e/{event.slug}/ops/control/").status_code == 200
    assert b"Help" in c.get(f"/e/{event.slug}/staff/").content
    assert c.get(f"/api/v1/events/{event.slug}/helpdesk-requests/").json()["count"] == 1
    assert c.get(f"/api/v1/events/{event.slug}/lost-found/?kind=found").json()["count"] == 2
    assert c.get(f"/api/v1/events/{event.slug}/faq/").json()["count"] == 2
    from apps.ops import services as ops
    from apps.ops.models import LogEntry
    ops.sink("helpdesk.request", {"category": "accessibility", "subject": "Ramp"}, event)
    assert LogEntry.objects.filter(text__contains="Accessibility request: Ramp").exists()
