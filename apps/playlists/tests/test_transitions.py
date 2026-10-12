# SPDX-License-Identifier: AGPL-3.0-or-later
"""Slide transitions (ADR-0051): playlist default, per-item override, program payload, pages, API, sync."""
import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.content import services as content
from apps.core.a11y import audit_url
from apps.core.models import AuditLog
from apps.playlists import services
from apps.playlists.models import Playlist, PlaylistItem
from conftest import login_2fa


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def layouts(admin, event):
    out = []
    for name in ("One", "Two"):
        lay = content.create_layout(event, name=name, key=name.lower(), actor=admin)
        content.publish_layout(lay, actor=admin)
        out.append(lay)
    return out


@pytest.mark.django_db
def test_defaults_change_nothing(admin, event, layouts):
    pl = services.save_playlist(Playlist(event=event, name="Loop"), actor=admin)
    item = services.save_item(PlaylistItem(playlist=pl, layout=layouts[0]), actor=admin)
    assert (pl.transition, pl.transition_ms, item.transition, item.transition_ms) == ("none", 600, "", None)
    assert item.effective_transition() == ("none", 600)
    # no key in the program: screens cut, exactly as before
    assert "transition" not in services.playlist_payload(pl)["items"][0]


@pytest.mark.django_db
def test_playlist_default_item_override_and_payload(admin, event, layouts):
    one, two = layouts
    inner = services.save_playlist(Playlist(event=event, name="Inner", transition="zoom"), actor=admin)
    services.save_item(PlaylistItem(playlist=inner, layout=two), actor=admin)
    pl = services.save_playlist(Playlist(event=event, name="Loop", transition="fade", transition_ms=800,
                                         is_default=True), actor=admin)
    services.save_item(PlaylistItem(playlist=pl, layout=one), actor=admin)
    services.save_item(PlaylistItem(playlist=pl, layout=two, transition="slide-left", transition_ms=1200),
                       actor=admin)
    services.save_item(PlaylistItem(playlist=pl, layout=one, transition="none"), actor=admin)
    services.save_item(PlaylistItem(playlist=pl, child=inner, transition="slide-up"), actor=admin)
    items = services.playlist_payload(pl)["items"]
    assert items[0]["transition"] == {"effect": "fade", "ms": 800}
    assert items[1]["transition"] == {"effect": "slide-left", "ms": 1200}
    assert "transition" not in items[2]  # an item can turn the playlist's transition off
    assert "transition" not in items[3]  # a nested playlist brings its own
    program = services.build_program(event, services.Target(group=None))
    assert program["playlists"][str(inner.pk)]["items"][0]["transition"] == {"effect": "zoom", "ms": 600}
    entry = AuditLog.objects.filter(action="playlist.item_added").order_by("-pk")[2]
    assert entry.changes["transition"] == "slide-left" and entry.changes["transition_ms"] == 1200
    with pytest.raises(ValidationError):
        services.save_item(PlaylistItem(playlist=pl, layout=one, transition_ms=99_999), actor=admin)
    with pytest.raises(ValidationError):
        services.save_item(PlaylistItem(playlist=pl, layout=one, transition="spin"), actor=admin)


@pytest.mark.django_db
def test_pages(client, admin, event, layouts):
    login_2fa(client, admin)
    one, two = layouts
    client.post("/e/demo/playlists/lists/", {"new-name": "Loop", "new-mode": "ordered", "new-default_duration": 10,
                                             "new-transition": "fade", "new-transition_ms": 700})
    pl = Playlist.objects.get(name="Loop")
    assert (pl.transition, pl.transition_ms) == ("fade", 700)
    url = f"/e/demo/playlists/lists/{pl.pk}/"
    assert client.post(url, {"action": "add", "add-layout": one.pk, "add-weight": 1, "add-enabled": "on",
                             "add-transition": "zoom", "add-transition_ms": 400}).status_code == 302
    assert client.post(url, {"action": "add", "add-layout": two.pk, "add-weight": 1,
                             "add-enabled": "on"}).status_code == 302
    first, second = pl.items.all()
    assert (first.transition, first.transition_ms, second.transition) == ("zoom", 400, "")
    # change an item's transition from the list
    client.post(url, {"action": "transition", "item": second.pk, "transition": "slide-up"})
    assert PlaylistItem.objects.get(pk=second.pk).transition == "slide-up"
    # a settings form without the transition fields keeps them
    client.post(url, {"meta-name": "Loop", "meta-mode": "shuffle", "meta-default_duration": 8})
    pl.refresh_from_db()
    assert (pl.mode, pl.transition, pl.transition_ms) == ("shuffle", "fade", 700)
    r = client.post(url, {"meta-name": "Loop", "meta-mode": "ordered", "meta-default_duration": 8,
                          "meta-transition": "fade", "meta-transition_ms": 9000})
    assert r.status_code == 200 and Playlist.objects.get(pk=pl.pk).transition_ms == 700
    page = client.get(url).content.decode()
    assert "Transition" in page and "Playlist default (Fade)" in page
    assert audit_url(client, url) == []


@pytest.mark.django_db
def test_api(admin, event, layouts):
    one, two = layouts
    _tok, raw = ServiceToken.issue(name="t", owner=admin, scopes=["playlists:write"])
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    base = "/api/v1/events/demo/playlists/"
    r = api.post(base, {"name": "Loop", "transition": "slide-left", "transition_ms": 900, "items": [
        {"layout": str(one.pk)}, {"layout": str(two.pk), "transition": "fade", "transition_ms": 300}]}, format="json")
    assert r.status_code == 201, r.content
    body = r.json()
    assert (body["transition"], body["transition_ms"]) == ("slide-left", 900)
    assert [(i["transition"], i["transition_ms"]) for i in body["items"]] == [("", None), ("fade", 300)]
    assert api.post(base, {"name": "Bad", "transition": "spin"}, format="json").status_code == 400
    assert api.post(base, {"name": "Long", "transition_ms": 6000}, format="json").status_code == 400
    # without the fields: no transition (the behaviour before ADR-0051)
    r = api.post(base, {"name": "Plain"}, format="json")
    assert (r.json()["transition"], r.json()["transition_ms"]) == ("none", 600)


@pytest.mark.django_db
def test_venue_node_snapshot_carries_transitions(admin, event, layouts):
    from apps.nodes import snapshot

    pl = services.save_playlist(Playlist(event=event, name="Loop", transition="zoom", transition_ms=450),
                                actor=admin)
    services.save_item(PlaylistItem(playlist=pl, layout=layouts[0], transition="fade", transition_ms=250),
                       actor=admin)
    models = {m.label: m for m in snapshot.sync_models()}
    rows = {label: snapshot.serialize(models[label].queryset(event))[0]["fields"]
            for label in ("playlists.Playlist", "playlists.PlaylistItem")}
    assert (rows["playlists.Playlist"]["transition"], rows["playlists.Playlist"]["transition_ms"]) == ("zoom", 450)
    assert (rows["playlists.PlaylistItem"]["transition"], rows["playlists.PlaylistItem"]["transition_ms"]) == (
        "fade", 250)


@pytest.mark.django_db
def test_pack_load_checks_transitions(admin, event, layouts):
    from types import SimpleNamespace

    from apps.playlists import packs

    one = layouts[0]
    warnings: list[str] = []
    ctx = SimpleNamespace(actor=admin, request=None, ids={"L1": str(one.pk)}, warn=warnings.append)
    packs.load(event, [
        {"id": "a", "name": "Old pack", "items": [{"layout": "L1"}]},  # written before ADR-0051
        {"id": "b", "name": "Odd pack", "transition": "spin", "transition_ms": "x",
         "items": [{"layout": "L1", "transition": "<script>", "transition_ms": 10 ** 9}]},
    ], ctx)
    old = Playlist.objects.get(name="Old pack")
    assert (old.transition, old.transition_ms, old.items.get().transition, old.items.get().transition_ms) == (
        "none", 600, "", None)
    odd = Playlist.objects.get(name="Odd pack")
    assert (odd.transition, odd.transition_ms, odd.items.get().transition, odd.items.get().transition_ms) == (
        "none", 600, "", 5000)
    assert warnings == []
