# SPDX-License-Identifier: AGPL-3.0-or-later
"""Route graph (ADR-0026): unit and property tests of the routing rules, pages, API and export."""
import json
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from rest_framework.test import APIClient

from apps.accounts.models import ServiceToken
from apps.core.a11y import audit_url
from apps.events import services as event_services
from apps.venues import graph, routing
from apps.venues.models import Edge, Floor, Point, Zone
from conftest import login_2fa

N = routing.Node
L = routing.Link


def small_venue():
    """hall -- door -- exit -- assembly; stairs (not step-free) as a shortcut to a second exit"""
    nodes = [N("hall", "waypoint", 0, 0), N("door", "door", 10, 0), N("exit", "exit", 20, 0),
             N("meet", "assembly", 50, 0), N("stairs", "stairs", 0, 5, step_free=False),
             N("exit2", "exit", 0, 8), N("meet2", "assembly", 0, 30)]
    links = [L("hall", "door"), L("door", "exit"), L("exit", "meet"), L("hall", "stairs", step_free=False),
             L("stairs", "exit2", step_free=False), L("exit2", "meet2")]
    return routing.Graph.build(nodes, links)


def test_routes_pick_the_nearest_assembly_point():
    g = small_venue()
    table = routing.routes(g)
    assert table["hall"] == routing.Route(next="stairs", target="meet2", distance=30.0)
    assert routing.path(table, "hall") == ["hall", "stairs", "exit2", "meet2"]
    assert table["meet"] == routing.Route(next=None, target="meet", distance=0.0)
    # step-free: around the stairs
    free = routing.routes(g, step_free=True)
    assert free["hall"].target == "meet" and free["hall"].distance == 50.0 and "stairs" not in free
    # a blocked exit reroutes at once
    blocked = routing.routes(g, blocked=["exit2"])
    assert blocked["hall"].target == "meet" and routing.path(blocked, "hall") == ["hall", "door", "exit", "meet"]
    assert "exit2" not in blocked and routing.path(blocked, "exit2") == []


def test_exits_are_targets_without_assembly_points_and_one_way_edges():
    nodes = [N("a", "waypoint", 0, 0), N("b", "waypoint", 10, 0, level=1), N("x", "exit", 20, 0)]
    g = routing.Graph.build(nodes, [L("a", "b"), L("b", "x", one_way=True, length=3), L("x", "zzz"),
                                    L("a", "a")])
    table = routing.routes(g)
    assert table["a"].distance == pytest.approx(10 + routing.LEVEL_PENALTY + 3) and table["a"].target == "x"
    # the one-way edge cannot be walked back: from x there is no way to b (x is itself the target)
    g2 = routing.Graph.build(nodes, [L("x", "b", one_way=True), L("a", "b")])
    assert "b" not in routing.routes(g2) and "a" not in routing.routes(g2)
    # unreachable assembly point: fall back to exits
    g3 = routing.Graph.build([*nodes, N("m", "assembly", 99, 99)], [L("a", "b"), L("b", "x")])
    assert routing.routes(g3)["a"].target == "x"


def test_problems():
    assert routing.problems(routing.Graph.build([N("a", "waypoint")], [])) == [
        ("", "no exit or assembly point"), ("a", "no route to an exit or assembly point")]
    g = small_venue()
    assert routing.problems(g) == []
    g2 = routing.Graph.build([*g.nodes.values(), N("cellar", "waypoint", 0, 9)],
                             [L("cellar", "stairs", step_free=False)])
    issues = dict(routing.problems(g2))
    assert issues["cellar"] == "no route to an exit or assembly point"
    g3 = routing.Graph.build(list(g.nodes.values()), [L("hall", "stairs", step_free=False),
                                                       L("stairs", "exit2", step_free=False), L("exit2", "meet2")])
    assert ("hall", "no step-free route") in routing.problems(g3)


# ------------------------------------------------------------------ property tests
KINDS = ["waypoint", "door", "stairs", "exit", "assembly"]


@st.composite
def graphs(draw):
    n = draw(st.integers(min_value=1, max_value=9))
    nodes = [N(f"n{i}", draw(st.sampled_from(KINDS)), draw(st.integers(0, 50)), draw(st.integers(0, 50)),
               draw(st.integers(-1, 2)), draw(st.booleans())) for i in range(n)]
    pairs = draw(st.lists(st.tuples(st.integers(0, n - 1), st.integers(0, n - 1)), max_size=20))
    links = [L(f"n{a}", f"n{b}", one_way=draw(st.booleans()), step_free=draw(st.booleans()),
               length=draw(st.one_of(st.none(), st.integers(0, 40))))
             for a, b in pairs if a != b]
    blocked = draw(st.lists(st.sampled_from([x.id for x in nodes]), max_size=3))
    return routing.Graph.build(nodes, links), blocked, draw(st.booleans())


def brute_force(g, targets, blocked, step_free):
    """Bellman-Ford over the same rules: shortest distance from every usable node to any target."""
    ok = {n for n, node in g.nodes.items() if n not in blocked and (node.step_free or not step_free)}
    dist = {t: 0.0 for t in targets if t in ok}
    for _ in range(len(g.nodes)):
        for a in ok:
            for b, length, free in g.out[a]:
                if b in dist and b in ok and (free or not step_free):
                    dist[a] = min(dist.get(a, math.inf), dist[b] + length)
    return dist


@settings(max_examples=300, deadline=None)
@given(graphs())
def test_routes_are_shortest_and_consistent(case):
    g, blocked, step_free = case
    table = routing.routes(g, blocked=blocked, step_free=step_free)
    assembly = brute_force(g, g.targets("assembly", frozenset(blocked)), set(blocked), step_free)
    exits = brute_force(g, g.targets("exit", frozenset(blocked)), set(blocked), step_free)
    for node in g.nodes:
        expected = assembly.get(node, exits.get(node))
        if expected is None:
            assert node not in table
            continue
        route = table[node]
        assert route.distance == pytest.approx(expected)
        assert g.nodes[route.target].kind == ("assembly" if node in assembly else "exit")
        walk = routing.path(table, node)
        assert walk[0] == node and walk[-1] == route.target
        assert not set(walk) & set(blocked)
        if step_free:
            assert all(g.nodes[p].step_free for p in walk)
        if route.next is not None:  # each step is a real edge and the distances add up
            steps = [(b, length, free) for b, length, free in g.out[node] if b == route.next]
            assert any(math.isclose(length + table[route.next].distance, route.distance) and
                       (free or not step_free) for _b, length, free in steps)


# ------------------------------------------------------------------ database, pages, API, export
@pytest.fixture
def plan(venue):
    floor = Floor.objects.get(name="Ground")
    north = Zone.objects.get(name="North")
    pts = {k: Point.objects.create(venue=venue, floor=floor, zone=north, kind=kind, name=name, x=x, y=0)
           for k, kind, name, x in [("hall", "waypoint", "Hall centre", 0), ("door", "door", "Main door", 10),
                                    ("exit", "exit", "Exit A", 20), ("meet", "assembly", "Car park", 60)]}
    for a, b in [("hall", "door"), ("door", "exit"), ("exit", "meet")]:
        Edge.objects.create(venue=venue, a=pts[a], b=pts[b])
    return pts


def test_graph_from_database(venue, plan):
    table = graph.table(venue)
    assert table[str(plan["hall"].pk)].target == str(plan["meet"].pk)
    assert table[str(plan["hall"].pk)].distance == 60
    assert plan["meet"].evac_scope_chain()[-1] == ("assembly", str(plan["meet"].pk))
    assert str(plan["hall"]) == "Waypoint Hall centre"
    assert str(Edge.objects.get(a=plan["hall"])) == "Hall centre ↔ Main door"
    assert plan["hall"].level == 0
    report = graph.report(venue)
    assert report["problems"] == [] and report["rows"][-1]["target"] == plan["meet"]


def test_venue_page_edits_the_graph(admin_client, event, venue, plan):
    base = "/e/demo/venues/hall/"
    page = admin_client.get(base).content.decode()
    assert "Ways out" in page and "Car park" in page
    assert audit_url(admin_client, base) == []
    r = admin_client.post(base, {"part": "point", "point-kind": "exit", "point-name": "Side exit", "point-x": "2",
                                 "point-y": "9", "point-step_free": "on"})
    assert r.status_code == 302
    side = Point.objects.get(name="Side exit")
    assert side.venue == venue
    r = admin_client.post(base, {"part": "edge", "edge-a": str(plan["hall"].pk), "edge-b": str(side.pk),
                                 "edge-step_free": "on"})
    assert r.status_code == 302 and Edge.objects.filter(a=plan["hall"], b=side).exists()
    # the reverse pair and a loop are refused
    again = admin_client.post(base, {"part": "edge", "edge-a": str(side.pk), "edge-b": str(plan["hall"].pk)})
    assert again.status_code == 200 and b"already connected" in again.content
    loop = admin_client.post(base, {"part": "edge", "edge-a": str(side.pk), "edge-b": str(side.pk)})
    assert loop.status_code == 200
    page = admin_client.get(base).content.decode()
    assert "Side exit" in page
    admin_client.post(f"{base}point/{side.pk}/delete/")
    assert not Point.objects.filter(name="Side exit").exists() and Edge.objects.count() == 3


def test_api_points_edges_and_routes(event, admin, venue, plan, member):
    _tok, raw = ServiceToken.issue(name="ci", owner=admin, scopes=["venues:write"], event=event)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    r = api.post("/api/v1/points/", {"venue": str(venue.pk), "kind": "exit", "name": "Back exit", "x": 0,
                                     "y": 10}, format="json")
    assert r.status_code == 201, r.content
    back = r.json()["id"]
    r = api.post("/api/v1/edges/", {"venue": str(venue.pk), "a": str(plan["hall"].pk), "b": back,
                                    "length_m": 2}, format="json")
    assert r.status_code == 201, r.content
    routes = api.get("/api/v1/venues/hall/routes/").json()
    hall = routes[str(plan["hall"].pk)]
    assert hall["target"] == str(plan["meet"].pk)  # assembly points win over exits
    blocked = api.get(f"/api/v1/venues/hall/routes/?blocked={plan['exit'].pk}").json()
    assert blocked[str(plan["hall"].pk)]["target"] == back and blocked[str(plan["hall"].pk)]["distance"] == 2
    assert blocked[str(plan["hall"].pk)]["path"] == [str(plan["hall"].pk), back]
    assert api.get("/api/v1/venues/hall/routes/?step_free=1").status_code == 200
    # validation: points of another venue, loops
    other = event_services.create_event(name="X", slug="x", user=admin)
    from apps.venues.models import Venue

    far = Venue.objects.create(slug="far", name="Far")
    other.venues.add(far)
    far_point = Point.objects.create(venue=far, name="Far exit", kind="exit")
    bad = api.post("/api/v1/edges/", {"venue": str(venue.pk), "a": str(plan["hall"].pk), "b": str(far_point.pk)},
                   format="json")
    assert bad.status_code == 400
    loop = api.post("/api/v1/edges/", {"venue": str(venue.pk), "a": back, "b": back}, format="json")
    assert loop.status_code == 400
    wrong_zone = api.post("/api/v1/points/", {"venue": str(far.pk), "name": "x", "zone": str(plan["hall"].zone_id)},
                          format="json")
    assert wrong_zone.status_code == 400


def test_export_import_keeps_the_graph(event, admin, venue, plan):
    data = json.loads(json.dumps(event_services.export_event(event), default=str))
    exported = data["plugins"]["venues"][0]
    assert len(exported["points"]) == 4 and len(exported["edges"]) == 3
    exported["slug"] = "copy"
    exported["edges"].append({"a": "missing", "b": exported["points"][0]["id"]})
    exported["points"].append({"id": "odd", "kind": "spaceship", "name": "Odd"})
    copy, _ = event_services.import_event(data, user=admin)
    v = copy.venues.get()
    assert v.points.count() == 5 and v.edges.count() == 3
    assert v.points.get(name="Odd").kind == "waypoint"
    hall = v.points.get(name="Hall centre")
    assert hall.floor.name == "Ground" and hall.zone.name == "North"
    assert graph.table(v)[str(hall.pk)].distance == 60


def test_assembly_scope_kind(event, venue, plan, member, role, client):
    event_services.assign_role(event, member, role("crew"), scope_kind="assembly", scope_id=str(plan["meet"].pk))
    from apps.core.registry import registry

    choices = dict(registry.ensure_loaded().scope_kinds["assembly"].choices(event))
    assert choices == {str(plan["meet"].pk): "Hall · Car park"}
    login_2fa(client, member)
    assert client.get("/e/demo/venues/hall/").status_code == 200
