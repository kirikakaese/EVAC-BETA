# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt
import json
import socket
from unittest import mock

import pytest
import requests
from django.core.exceptions import ValidationError

from apps.core import modules, settings_store
from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.widgets import fetch, mapping, parse, services
from apps.widgets.models import CustomWidget, Feed
from conftest import login_2fa

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
PRIVATE = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))]

SCHEDULE = {"stage": "Main", "talks": [
    {"title": "Opening", "speaker": {"name": "Ada"}, "start": "2026-07-01T10:00:00+02:00", "seats": 120},
    {"title": "Keynote", "speaker": {"name": "Grace"}, "start": "2026-07-01T11:00:00+02:00", "seats": 80},
    {"title": "Closing", "speaker": {"name": "Linus"}, "start": "2026-07-01T17:00:00+02:00", "seats": "45"},
]}
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Camp news</title>
<item><title>Bar open</title><link>https://x.example.org/1</link>
<description>&lt;p&gt;Until &lt;b&gt;2&lt;/b&gt; am&lt;/p&gt;</description>
<pubDate>Wed, 01 Jul 2026 18:00:00 +0000</pubDate></item>
<item><title>Rain</title><link>https://x.example.org/2</link></item></channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Atom news</title>
<entry><title>Hello</title><link href="https://x.example.org/a"/><summary>Hi</summary><updated>2026-07-01T10:00:00Z</updated></entry></feed>"""
ICAL = (
    b"BEGIN:VCALENDAR\r\n"
    b"VERSION:2.0\r\n"
    b"X-WR-CALNAME:Stage A\r\n"
    b"BEGIN:VEVENT\r\n"
    b"UID:2\r\n"
    b"SUMMARY:Late show\r\n"
    b"DTSTART;TZID=Europe/Berlin:20260701T210000\r\n"
    b"DTEND;TZID=Europe/Berlin:20260701T220000\r\n"
    b"LOCATION:Stage A\r\n"
    b"END:VEVENT\r\n"
    b"BEGIN:VEVENT\r\n"
    b"UID:1\r\n"
    b"SUMMARY:Early\\, really early\r\n"
    b"  show\r\n"
    b"DTSTART:20260701T080000Z\r\n"
    b"DTEND:20260701T090000Z\r\n"
    b"RRULE:FREQ=DAILY\r\n"
    b"END:VEVENT\r\n"
    b"BEGIN:VEVENT\r\n"
    b"UID:3\r\n"
    b"SUMMARY:Cancelled\r\n"
    b"STATUS:CANCELLED\r\n"
    b"DTSTART;VALUE=DATE:20260702\r\n"
    b"END:VEVENT\r\n"
    b"BEGIN:VEVENT\r\n"
    b"UID:4\r\n"
    b"SUMMARY:All day\r\n"
    b"DTSTART;VALUE=DATE:20260703\r\n"
    b"END:VEVENT\r\n"
    b"END:VCALENDAR\r\n"
)
CSV = b"Room;Free\nHall A;12\nHall B;0\n"


class Resp:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}

    def iter_content(self, size):
        for i in range(0, len(self._body), size):
            yield self._body[i:i + size]

    def close(self):
        pass


@pytest.fixture
def public_dns():
    with mock.patch("apps.widgets.fetch.socket.getaddrinfo", return_value=PUBLIC) as m:
        yield m


# ------------------------------------------------------------------ fetching
def test_check_url_blocks_private_and_odd_urls():
    for bad in ["ftp://x.example.org/f", "file:///etc/passwd", "https://user:pw@x.example.org/", "http:///x"]:
        with pytest.raises(fetch.FetchError):
            fetch.check_url(bad)
    with mock.patch("apps.widgets.fetch.socket.getaddrinfo", return_value=PRIVATE):
        with pytest.raises(fetch.FetchError, match="private network"):
            fetch.check_url("http://sensor.local/")
        fetch.check_url("http://sensor.local/", allow_private=True)
    for addr in ["127.0.0.1", "169.254.169.254", "::1", "::ffff:10.0.0.1", "0.0.0.0", "224.0.0.1"]:
        fam = socket.AF_INET6 if ":" in addr else socket.AF_INET
        with mock.patch("apps.widgets.fetch.socket.getaddrinfo", return_value=[(fam, 1, 6, "", (addr, 80))]):
            with pytest.raises(fetch.FetchError):
                fetch.check_url("http://evil.example.org/")
    with mock.patch("apps.widgets.fetch.socket.getaddrinfo", side_effect=socket.gaierror):
        with pytest.raises(fetch.FetchError, match="Unknown host"):
            fetch.check_url("https://nowhere.invalid/")


def test_get_redirects_are_checked_again(public_dns):
    hops = [Resp(302, headers={"Location": "/next"}), Resp(200, b'{"ok": 1}', {"ETag": '"v1"',
                                                                                "Content-Type": "application/json"})]
    with mock.patch("apps.widgets.fetch.requests.get", side_effect=hops) as get:
        got = fetch.get("https://api.example.org/data", headers={"X-Key": "k"}, etag='"v0"')
    assert got.body == b'{"ok": 1}' and got.etag == '"v1"'
    assert get.call_args_list[1].args[0] == "https://api.example.org/next"
    assert get.call_args_list[0].kwargs["headers"]["If-None-Match"] == '"v0"'
    # a redirect into the private network is refused
    def dns(host, *a, **k):
        return PRIVATE if host == "internal" else PUBLIC
    with mock.patch("apps.widgets.fetch.socket.getaddrinfo", side_effect=dns), \
         mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(301, headers={"Location": "http://internal/"})):
        with pytest.raises(fetch.FetchError, match="private"):
            fetch.get("https://api.example.org/")
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(302, headers={"Location": "/loop"})):
        with pytest.raises(fetch.FetchError, match="Too many redirects"):
            fetch.get("https://api.example.org/")


def test_get_errors_and_limits(public_dns):
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(304)):
        assert fetch.get("https://api.example.org/", etag='"x"').status == 304
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(404)):
        with pytest.raises(fetch.FetchError, match="404"):
            fetch.get("https://api.example.org/")
    with mock.patch("apps.widgets.fetch.requests.get", side_effect=requests.ConnectionError("x")):
        with pytest.raises(fetch.FetchError, match="did not answer"):
            fetch.get("https://api.example.org/")
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, b"x" * (fetch.MAX_BYTES + 1))):
        with pytest.raises(fetch.FetchError, match="More than"):
            fetch.get("https://api.example.org/")


# ------------------------------------------------------------------ parsing
def test_parse_formats():
    assert parse.parse("json", json.dumps(SCHEDULE).encode()) == SCHEDULE
    with pytest.raises(parse.ParseError, match="Not valid JSON"):
        parse.parse("json", b"{nope")
    rss = parse.parse("rss", RSS)
    assert rss["title"] == "Camp news" and rss["items"][0]["summary"] == "Until 2 am"
    assert rss["items"][0]["link"] == "https://x.example.org/1" and rss["items"][1]["published"] == ""
    atom = parse.parse("rss", ATOM)
    assert atom["items"][0] == {"title": "Hello", "link": "https://x.example.org/a", "summary": "Hi",
                                "published": "2026-07-01T10:00:00Z", "author": ""}
    rdf = parse.parse("rss", b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                             b'xmlns="http://purl.org/rss/1.0/"><channel><title>R</title></channel>'
                             b"<item><title>One</title></item></rdf:RDF>")
    assert rdf["title"] == "R" and rdf["items"][0]["title"] == "One"
    with pytest.raises(parse.ParseError):
        parse.parse("rss", b"<html></html>")
    with pytest.raises(parse.ParseError):
        parse.parse("rss", b"<rss></rss>")
    with pytest.raises(parse.ParseError):
        parse.parse("rss", b'<!DOCTYPE x [<!ENTITY a "b">]><rss>&a;</rss>')  # defusedxml refuses entities
    cal = parse.parse("ical", ICAL)
    assert cal["name"] == "Stage A"
    assert [e["summary"] for e in cal["events"]] == ["Early, really early show", "Late show", "All day"]
    assert cal["events"][0]["start"] == "2026-07-01T08:00:00+00:00" and cal["events"][0]["repeats"] == "FREQ=DAILY"
    assert cal["events"][1]["start"] == "2026-07-01T21:00:00+02:00" and cal["events"][2]["start"] == "2026-07-03"
    with pytest.raises(parse.ParseError, match="VCALENDAR"):
        parse.parse("ical", b"hello")
    table = parse.parse("csv", CSV)
    assert table == {"columns": ["Room", "Free"], "rows": [{"Room": "Hall A", "Free": "12"},
                                                          {"Room": "Hall B", "Free": "0"}]}
    with pytest.raises(parse.ParseError):
        parse.parse("csv", b"")
    assert parse.parse("csv", "a,b\n1,2\n".encode("latin-1"))["rows"] == [{"a": "1", "b": "2"}]


# ------------------------------------------------------------------ mapping
def test_paths_and_rows():
    assert mapping.tokens("$.talks[*].speaker['name']") == ["talks", "*", "speaker", "name"]
    assert mapping.tokens('$["a b"][-1]') == ["a b", -1]
    with pytest.raises(mapping.PathError):
        mapping.tokens("$.talks[?(@.x)]")
    assert mapping.select(SCHEDULE, "$.talks[*].title") == ["Opening", "Keynote", "Closing"]
    assert mapping.first(SCHEDULE, "talks[-1].speaker.name") == "Linus"
    assert mapping.select({"a": {"x": 1, "y": 2}}, "$.a[*]") == [1, 2]
    assert mapping.select(SCHEDULE, "$.talks[9]") == [] and mapping.first(SCHEDULE, "nope") is None
    assert mapping.items(SCHEDULE, "$.talks") == SCHEDULE["talks"]
    assert len(mapping.items(SCHEDULE, "$.talks[*]")) == 3
    rows = mapping.rows(SCHEDULE, "$.talks", {"title": "title", "subtitle": "speaker.name", "value": "seats",
                                              "time": "start", "label": "speaker"}, limit=2)
    assert rows == [{"title": "Opening", "subtitle": "Ada", "value": 120, "label": "Ada",
                     "time": "2026-07-01T10:00:00+02:00"},
                    {"title": "Keynote", "subtitle": "Grace", "value": 80, "label": "Grace",
                     "time": "2026-07-01T11:00:00+02:00"}]
    late = dt.datetime(2026, 7, 1, 12, tzinfo=dt.UTC)
    assert [r["title"] for r in mapping.rows(SCHEDULE, "talks", {"title": "title", "time": "start"},
                                             upcoming=True, now=late)] == ["Closing"]
    rss_rows = mapping.rows(parse.parse("rss", RSS), "$.items", {"title": "title", "time": "published"},
                            upcoming=True, now=dt.datetime(2026, 7, 1, 12, tzinfo=dt.UTC))
    assert [r["title"] for r in rss_rows] == ["Bar open", "Rain"]  # RFC 822 dates; items without time stay
    tree = mapping.tree({"a b": [1, 2, 3, 4], "n": None})
    assert tree["children"][0]["path"] == '$["a b"]' and len(tree["children"][0]["children"]) == 3
    assert tree["children"][1] == {"key": "n", "path": "$.n", "kind": "value", "value": None}


# ------------------------------------------------------------------ services
def make_feed(event, admin, **kw):
    kw.setdefault("name", "Schedule")
    kw.setdefault("url", "https://api.example.org/schedule.json")
    with mock.patch("apps.widgets.fetch.socket.getaddrinfo", return_value=PUBLIC):
        return services.save_feed(Feed(event=event, **kw), actor=admin, auth_header=kw.pop("auth", None))


def test_feed_fetch_cycle(event, admin, public_dns, django_capture_on_commit_callbacks):
    feed = services.save_feed(Feed(event=event, name="S", url="https://api.example.org/s.json", poll_seconds=5),
                              actor=admin, auth_header="X-Api-Key: secret")
    assert feed.poll_seconds == services.MIN_POLL and "secret" not in feed.auth_header_encrypted
    log = AuditLog.objects.get(action="widgets.feed_created")
    assert log.changes["auth_header"] == "changed" and "secret" not in json.dumps(log.changes)
    w = services.save_widget(CustomWidget(event=event, name="Talks", feed=feed, items_path="$.talks",
                                          fields={"title": "title", "value": "seats"}), actor=admin)
    with mock.patch("apps.widgets.fetch.requests.get",
                    return_value=Resp(200, json.dumps(SCHEDULE).encode(), {"ETag": '"e1"'})) as get, \
         mock.patch("apps.screens.channel.send") as send:
        from django.test import Client

        from apps.screens import services as screen_services

        c = Client()
        data = c.post("/player/api/pair/", data="{}", content_type="application/json").json()
        screen_services.pair(event, data["code"], actor=admin, name="Foyer")
        with django_capture_on_commit_callbacks(execute=True):
            assert services.fetch_feed(feed) is True
    assert get.call_args.kwargs["headers"]["X-Api-Key"] == "secret"
    assert send.call_args.args[1] == "data.changed"
    feed.refresh_from_db()
    assert feed.status == "ok" and feed.etag == '"e1"' and feed.snapshot == SCHEDULE
    payload = services.widget_payload(w)
    assert payload["rows"][0] == {"title": "Opening", "value": 120} and payload["stale"] is False
    # unchanged data: no new notification; 304: nothing changes
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, json.dumps(SCHEDULE).encode())):
        assert services.fetch_feed(feed) is False
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(304)):
        assert services.fetch_feed(feed) is False
    # errors keep the last good snapshot and mark the data stale
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(500)):
        assert services.fetch_feed(feed) is False
    feed.refresh_from_db()
    assert feed.status == "error" and "500" in feed.error and feed.snapshot == SCHEDULE
    w.refresh_from_db()
    assert services.widget_payload(w)["stale"] is True and services.widget_payload(w)["rows"]
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, b"not json")):
        services.fetch_feed(feed)
    assert Feed.objects.get(pk=feed.pk).error.startswith("Not valid JSON")
    with mock.patch("apps.widgets.services.MAX_SNAPSHOT", 10), \
         mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, json.dumps(SCHEDULE).encode())):
        services.fetch_feed(feed)
    assert "too large" in Feed.objects.get(pk=feed.pk).error


def test_fetch_due_and_sources(event, admin, public_dns):
    from apps.widgets.tasks import fetch_due, fetch_feed

    feed = make_feed(event, admin)
    src = services.save_feed(Feed(event=event, name="Event", kind="source", source="event.info"), actor=admin)
    assert src.url == ""
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, b"[1]")):
        assert fetch_due() == 2
        assert fetch_due() == 0  # not due again yet
        assert fetch_feed(str(feed.pk)) is False and fetch_feed("00000000-0000-0000-0000-000000000000") is False
    src.refresh_from_db()
    assert src.snapshot["name"] == "Demo Camp" and src.snapshot["venues"] == [{"name": "Hall"}]
    Feed.objects.filter(pk=src.pk).update(source="gone.source")
    src.refresh_from_db()
    services.fetch_feed(src)
    assert "not available" in Feed.objects.get(pk=src.pk).error


def test_on_air_source(event, admin):
    from apps.announcements import services as ann
    from apps.announcements.models import Announcement, Level

    ann.ensure_defaults(event)
    a = Announcement(event=event, level=Level.objects.get(event=event, key="info"), title="Bar open",
                     channels=["staff"])
    ann.save_draft(a, actor=admin)
    ann.submit(a, actor=admin)
    feed = services.save_feed(Feed(event=event, name="On air", kind="source", source="announcements.on_air"),
                              actor=admin)
    services.fetch_feed(feed)
    assert feed.snapshot["announcements"][0]["title"] == "Bar open"
    modules.set_event(event, "announcements", False, user=admin)
    assert "announcements.on_air" not in dict(services.source_choices(event))


def test_validation(event, admin, public_dns):
    with pytest.raises(ValidationError, match="URL is needed"):
        services.save_feed(Feed(event=event, name="x"), actor=admin)
    with pytest.raises(ValidationError, match="data source"):
        services.save_feed(Feed(event=event, name="x", kind="source", source="nope"), actor=admin)
    with mock.patch("apps.widgets.fetch.socket.getaddrinfo", return_value=PRIVATE):
        with pytest.raises(ValidationError, match="private network"):
            services.save_feed(Feed(event=event, name="x", url="http://10.0.0.5/x"), actor=admin)
        settings_store.save("widgets", "instance", "", {"allow_private_networks": True}, user=admin)
        services.save_feed(Feed(event=event, name="x", url="http://10.0.0.5/x"), actor=admin)
    feed = Feed.objects.get(name="x")
    for fields, path in [({"title": "a[?(x)]"}, "$"), ({"nope": "a"}, "$"), ({}, "$..x")]:
        with pytest.raises(ValidationError):
            services.save_widget(CustomWidget(event=event, name="w", feed=feed, items_path=path, fields=fields),
                                 actor=admin)
    from apps.events import services as event_services

    other = event_services.create_event(name="Other", slug="other", user=admin)
    with pytest.raises(ValidationError, match="another event"):
        services.save_widget(CustomWidget(event=other, name="w", feed=feed), actor=admin)
    w = services.save_widget(CustomWidget(event=event, name="w", feed=feed), actor=admin)
    with pytest.raises(ValidationError, match="Widgets use this feed"):
        services.delete_feed(feed, actor=admin)
    assert services.widget_rows(w) == []  # no snapshot yet
    CustomWidget.objects.filter(pk=w.pk).update(items_path="$[?bad]")
    feed.snapshot = [1]
    feed.save()
    w.refresh_from_db()
    assert services.widget_rows(w) == []
    services.delete_widget(w, actor=admin)
    services.delete_feed(feed, actor=admin)
    assert not Feed.objects.exists()


# ------------------------------------------------------------------ pages and screens
def test_builder_pages(client, admin, event, public_dns):
    login_2fa(client, admin)
    assert client.get("/e/demo/widgets/").status_code == 200
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, json.dumps(SCHEDULE).encode())):
        r = client.post("/e/demo/widgets/feeds/new/", {"name": "Schedule", "kind": "json",
                                                        "url": "https://api.example.org/s.json", "poll_seconds": 300,
                                                        "enabled": "on"})
    feed = Feed.objects.get()
    assert r["Location"] == f"/e/demo/widgets/feeds/{feed.pk}/" and feed.status == "ok"
    page = client.get(r["Location"]).content.decode()
    assert "$.talks[0].speaker.name" in page and "Make a widget" in page
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, json.dumps(SCHEDULE).encode())):
        assert client.post(f"/e/demo/widgets/feeds/{feed.pk}/fetch/").status_code == 302
    bad = client.post("/e/demo/widgets/feeds/new/", {"name": "x", "kind": "json", "url": "ftp://x.example.org",
                                                      "poll_seconds": 300})
    assert bad.status_code == 200
    assert client.get(f"/e/demo/widgets/new/?feed={feed.pk}").status_code == 200
    data = {"name": "Talks", "feed": feed.pk, "visual": "list", "items_path": "$.talks", "f_title": "title",
            "f_subtitle": "speaker.name", "f_time": "start", "limit": 5, "heading": "Next on Main"}
    r = client.post("/e/demo/widgets/new/", data)
    w = CustomWidget.objects.get()
    assert r.status_code == 302 and w.fields == {"title": "title", "subtitle": "speaker.name", "time": "start"}
    assert w.options == {"limit": 5, "heading": "Next on Main", "upcoming": False}
    page = client.get(f"/e/demo/widgets/{w.pk}/")
    assert page.context["config"]["data"][str(w.pk)]["rows"][0]["title"] == "Opening"
    assert b"preview-config" in page.content and b"3 items" in page.content
    bad = client.post(f"/e/demo/widgets/{w.pk}/", {**data, "f_title": "a[?x]"})
    assert bad.status_code == 200 and bad.context["form"].errors
    assert audit_url(client, "/e/demo/widgets/") == []
    assert audit_url(client, f"/e/demo/widgets/feeds/{feed.pk}/") == []
    assert audit_url(client, f"/e/demo/widgets/{w.pk}/") == []
    # the editor offers the widget and its rows
    from apps.content.layout_views import editor_choices

    choices = editor_choices(event)
    assert choices["dataWidgets"] == [{"value": str(w.pk), "label": "Talks", "visual": "list"}]
    assert choices["widgetData"][str(w.pk)]["rows"]
    client.post(f"/e/demo/widgets/feeds/{feed.pk}/delete/")
    assert Feed.objects.exists()  # still used
    client.post(f"/e/demo/widgets/{w.pk}/delete/")
    client.post(f"/e/demo/widgets/feeds/{feed.pk}/delete/")
    assert not Feed.objects.exists() and not CustomWidget.objects.exists()


def test_permissions_and_module_switch(client, member, admin, event, public_dns):
    feed = make_feed(event, admin)
    login_2fa(client, member)  # viewer: may look, not change
    assert client.get("/e/demo/widgets/").status_code == 200
    assert client.post(f"/e/demo/widgets/feeds/{feed.pk}/", {"name": "x"}).status_code == 403
    assert client.post(f"/e/demo/widgets/feeds/{feed.pk}/fetch/").status_code == 403
    assert client.post("/e/demo/widgets/new/", {"name": "x"}).status_code == 403
    modules.set_event(event, "widgets", False, user=admin)
    assert client.get("/e/demo/widgets/").status_code == 404
    from apps.content.layout_views import editor_choices

    assert "dataWidgets" not in editor_choices(event)


def test_player_data_endpoint(client, admin, event, public_dns):
    from apps.screens import services as screen_services

    feed = make_feed(event, admin)
    with mock.patch("apps.widgets.fetch.requests.get", return_value=Resp(200, json.dumps(SCHEDULE).encode())):
        services.fetch_feed(feed)
    w = services.save_widget(CustomWidget(event=event, name="Seats", feed=feed, items_path="$.talks",
                                          fields={"label": "title", "value": "seats"}, visual="bars"), actor=admin)
    assert client.get("/player/api/widgets/data/").status_code == 401
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    screen_services.pair(event, data["code"], actor=admin, name="Foyer")
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    got = client.get("/player/api/widgets/data/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["widgets"]
    assert got[str(w.pk)]["visual"] == "bars" and got[str(w.pk)]["rows"][2] == {"label": "Closing", "value": "45"}
    modules.set_event(event, "widgets", False, user=admin)
    assert client.get("/player/api/widgets/data/", HTTP_AUTHORIZATION=f"Bearer {token}").json() == {"widgets": {}}


def test_layout_accepts_data_element(admin, event):
    from apps.content import layout_format as lf

    data = {"format": 1, "width": 1920, "height": 1080, "elements": [
        {"id": "d", "type": "data", "frame": {"x": 0, "y": 0, "w": 50, "h": 50},
         "props": {"widget": "6f0c8f5e-2a7b-4b1e-9c3d-1a2b3c4d5e6f", "title": "Seats"}}]}
    assert lf.validate(data) == []
    data["elements"][0]["props"]["widget"] = "nope"
    assert lf.validate(data)
