# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inventory (ADR-0042): asset tags, lend/return with signature and photo, reminders, labels, map, API."""
import base64
import datetime as dt
import io
from unittest import mock

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.core import modules, settings_store
from apps.core.a11y import check_html
from apps.inventory import panels, services
from apps.inventory.models import Category, Item, Loan, Note
from conftest import login_2fa

pytestmark = pytest.mark.django_db


def png_bytes(size=(60, 20)):
    b = io.BytesIO()
    Image.new("RGB", size, "white").save(b, "PNG")
    return b.getvalue()


def sig():
    return "data:image/png;base64," + base64.b64encode(png_bytes()).decode()


@pytest.fixture
def radio(event, admin):
    cat = Category.objects.create(event=event, name="Radios", loan_hours=8)
    return services.save_item(Item(event=event, name="Radio", category=cat), actor=admin)[0]


def test_tags_and_copies(event, admin):
    made = services.save_item(Item(event=event, name="Radio"), actor=admin, copies=3)
    assert [i.asset_tag for i in made] == ["EV-0001", "EV-0002", "EV-0003"]
    settings_store.save("inventory", "event", str(event.pk), {"tag_prefix": "R-"}, event=event)
    assert services.save_item(Item(event=event, name="Key"), actor=admin)[0].asset_tag == "R-0001"
    services.save_item(Item(event=event, name="Own", asset_tag="SPECIAL"), actor=admin)
    with pytest.raises(ValidationError, match="taken"):
        services.save_item(Item(event=event, name="Dup", asset_tag="SPECIAL"), actor=admin)
    with pytest.raises(ValidationError):
        services.save_item(Item(event=event, name=" "), actor=admin)
    edited = made[0]
    edited.name = "Radio TH-1"
    assert services.save_item(edited, actor=admin) == [edited]


def test_lend_and_return(event, admin, radio, user):
    with mock.patch("apps.core.webhooks.emit") as emit:
        loan = services.lend(radio, borrower="", borrower_user=user, actor=admin, signature=sig(),
                             photo=SimpleUploadedFile("out.png", png_bytes(), "image/png"),
                             due_at=timezone.now() + dt.timedelta(hours=2))
    radio.refresh_from_db()
    assert radio.status == "lent" and loan.borrower == str(user) and loan.signature and loan.photo_out
    with pytest.raises(ValidationError, match="not available"):
        services.lend(radio, borrower="Bob", actor=admin)
    services.return_item(loan, condition="damaged", notes="cracked antenna", actor=admin)
    radio.refresh_from_db()
    assert radio.status == "maintenance"
    assert Note.objects.get(item=radio).kind == "damage"
    with pytest.raises(ValidationError, match="Already"):
        services.return_item(loan, actor=admin)
    services.add_note(radio, "fixed", kind="maintenance", status="available", actor=admin)
    radio.refresh_from_db()
    assert radio.status == "available"
    with pytest.raises(ValidationError):
        services.add_note(radio, "", kind="note", actor=admin)
    with pytest.raises(ValidationError):
        services.add_note(radio, "x", kind="note", status="lent", actor=admin)
    assert emit.call_count == 0  # on commit only


def test_signature_validation(event, admin, radio):
    for bad in ["data:image/png;base64,!!!", "data:image/jpeg;base64,AAAA",
                "data:image/png;base64," + base64.b64encode(b"GIF89a").decode()]:
        with pytest.raises(ValidationError, match="signature"):
            services.lend(radio, borrower="Bob", actor=admin, signature=bad)
    with pytest.raises(ValidationError, match="future"):
        services.lend(radio, borrower="Bob", actor=admin, due_at=timezone.now() - dt.timedelta(minutes=1))
    with pytest.raises(ValidationError, match="Who"):
        services.lend(radio, borrower=" ", actor=admin)


def test_overdue_reminder_once(event, admin, radio, user):
    loan = services.lend(radio, borrower="Ann", borrower_user=user, actor=admin,
                         due_at=timezone.now() + dt.timedelta(minutes=5))
    later = timezone.now() + dt.timedelta(minutes=10)
    with mock.patch("apps.core.webhooks.emit") as emit:
        assert services.remind_overdue(later) == 1
        assert services.remind_overdue(later) == 0
    assert emit.call_args[0][0] == "inventory.overdue"
    from apps.core.models import Notification
    assert Notification.objects.filter(user=user, title__contains=radio.asset_tag).exists()
    loan.refresh_from_db()
    assert loan.reminded_at is not None
    from apps.ops import services as ops
    from apps.ops.models import LogEntry
    ops.sink("inventory.overdue", services.payload_of(loan), event)
    assert LogEntry.objects.filter(event=event, text__contains="Not returned").exists()


def test_pages_lend_with_signature_and_return(client, event, admin, radio):
    c = login_2fa(client, admin)
    base = f"/e/{event.slug}/inventory/"
    r = c.get(f"{base}t/{radio.asset_tag}/")
    assert r.status_code == 302 and r.url.endswith(f"/inventory/{radio.pk}/")
    page = c.get(r.url).content.decode()
    assert "<svg" in page and "data-signature" in page and check_html(page) == []
    settings_store.save("inventory", "event", str(event.pk), {"signature_required": True}, event=event)
    c.post(f"{base}{radio.pk}/lend/", {"lend-borrower": "Ada"})
    assert not Loan.objects.exists()  # signature missing
    c.post(f"{base}{radio.pk}/lend/", {"lend-borrower": "Ada", "lend-signature": sig(), "lend-contact": "DECT 1"})
    loan = Loan.objects.get()
    assert loan.contact == "DECT 1"
    for url in ["", f"{radio.pk}/", "?q=ada", "?status=lent", f"?category={radio.category_id}", "labels/",
                f"labels/?from={radio.asset_tag}&to={radio.asset_tag}", "new/", f"{radio.pk}/edit/"]:
        r = c.get(base + url)
        assert r.status_code == 200, url
        assert check_html(r.content.decode()) == [], url
    assert b"Ada" in c.get(base + "?q=ada").content
    c.post(f"{base}{radio.pk}/return/", {"back-condition": "ok"})
    c.post(f"{base}{radio.pk}/return/", {"back-condition": "ok"})  # offline replay: harmless
    loan.refresh_from_db()
    assert loan.returned_at is not None and Item.objects.get(pk=radio.pk).status == "available"
    c.post(f"{base}{radio.pk}/note/", {"note-kind": "maintenance", "note-text": "new battery"})
    assert Note.objects.filter(text="new battery").exists()
    r = c.post(base + "new/", {"name": "Key", "copies": 3})
    assert r.status_code == 302 and "labels/?from=" in r.url and Item.objects.filter(name="Key").count() == 3
    c.post(base, {"cat-name": "Tools", "cat-loan_hours": 0})
    assert Category.objects.filter(name="Tools").exists()


def test_permissions_dashboard_staff_card(client, event, user, member, radio, admin):
    client.force_login(user)  # viewer: sees, may not lend or edit
    assert client.get(f"/e/{event.slug}/inventory/").status_code == 200
    assert client.post(f"/e/{event.slug}/inventory/{radio.pk}/lend/", {"lend-borrower": "x"}).status_code == 403
    assert client.get(f"/e/{event.slug}/inventory/new/").status_code == 403
    services.lend(radio, borrower="Me", borrower_user=user, actor=admin,
                  due_at=timezone.now() + dt.timedelta(hours=1))
    Loan.objects.update(due_at=timezone.now() - dt.timedelta(minutes=1))
    r = client.get(f"/e/{event.slug}/staff/")
    assert radio.asset_tag.encode() in r.content and b"overdue" in r.content
    from django.test import RequestFactory

    req = RequestFactory().get("/")
    req.user, req.session = user, {}
    ctx = panels.dashboard(req, event)
    assert ctx["out"] == 1 and len(ctx["overdue"]) == 1
    modules.set_instance("inventory", False)
    assert client.get(f"/e/{event.slug}/inventory/").status_code == 404


def test_map_layer(event, admin, venue, radio):
    from apps.venues.models import Building, Floor

    floor = Floor.objects.create(building=Building.objects.create(venue=venue, name="B"), name="G", level=0)
    services.map_place(event, str(radio.pk), floor=floor, x=4.0, y=2.0, facing=None, actor=admin)
    rows = services.map_items(event, venue)
    assert rows[0]["placed"] and rows[0]["x"] == 4.0 and rows[0]["state"] == "available"
    services.map_rescale(floor, 2.0)
    radio.refresh_from_db()
    assert (radio.position_x, radio.position_y) == (8.0, 4.0)
    services.map_place(event, str(radio.pk), floor=None, x=None, y=None, facing=None, actor=admin)
    radio.refresh_from_db()
    assert radio.floor is None
    with pytest.raises(ValidationError):
        services.map_place(event, "nope", floor=None, x=None, y=None, facing=None, actor=admin)


def test_api(client, event, admin, radio):
    c = login_2fa(client, admin)
    services.lend(radio, borrower="Ada", actor=admin)
    items = c.get(f"/api/v1/events/{event.slug}/inventory-items/").json()["results"]
    assert items[0]["loan"]["borrower"] == "Ada" and items[0]["status"] == "lent"
    assert c.get(f"/api/v1/events/{event.slug}/inventory-items/?status=available").json()["count"] == 0
    assert c.get(f"/api/v1/events/{event.slug}/loans/?open=1").json()["count"] == 1
