# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screen directions from the route graph (ADR-0030)."""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.evacuation import guidance
from apps.evacuation.guidance import Arrow, Kind, Place
from apps.venues import routing
from apps.venues.routing import Link, Node


def corridor():
    """W1 -- W2 -- EXIT east, and an assembly point A north of W1 (preferred target)."""
    nodes = [Node("w1", "waypoint", 0, 0), Node("w2", "waypoint", 20, 0), Node("ex", "exit", 40, 0),
             Node("a", "assembly", 0, -30)]
    links = [Link("w1", "w2"), Link("w2", "ex"), Link("w1", "a")]
    return routing.Graph.build(nodes, links)


@pytest.mark.parametrize(("bearing", "facing", "arrow"), [
    (0, 180, Arrow.AHEAD),  # screen looks south, people look north, exit north
    (90, 180, Arrow.RIGHT),
    (270, 180, Arrow.LEFT),
    (180, 180, Arrow.BACK),
    (45, 180, Arrow.AHEAD_RIGHT),
    (0, 0, Arrow.BACK),  # screen looks north: people look south, exit north is behind them
    (0, 90, Arrow.RIGHT),  # screen looks east: people look west, north is on their right
    (22, 180, Arrow.AHEAD), (23, 180, Arrow.AHEAD_RIGHT), (337.6, 180, Arrow.AHEAD),
])
def test_relative(bearing, facing, arrow):
    assert guidance.relative(bearing, facing) is arrow


def test_bearing():
    assert guidance.bearing(0, 0, 0, -10) == 0 and guidance.bearing(0, 0, 10, 0) == 90
    assert guidance.bearing(0, 0, 0, 10) == 180 and guidance.bearing(0, 0, -10, 0) == 270


def test_route_prefers_assembly_and_recomputes_when_blocked():
    g = corridor()
    table = routing.routes(g)
    place = Place(5, 5, facing=180)  # south of the corridor near w1, display looks south
    got = guidance.route(g, table, place, g.nodes)
    # the nearest point (w1) leads to the assembly point; never a straight line through walls to "a"
    assert got.kind is Kind.ROUTE and got.target == "a" and got.toward == "w1"
    assert got.arrow is Arrow.AHEAD_LEFT and got.distance == pytest.approx(37.1, abs=0.1)
    # at the same distance from two points, the shorter route wins
    tie = guidance.route(g, table, Place(10, 0, facing=180), g.nodes)
    assert tie.toward == "w1" and tie.target == "a"
    place = Place(15, 5, facing=180)
    assert guidance.route(g, table, place, g.nodes).toward == "w2"
    blocked = routing.routes(g, blocked={"a"})
    got = guidance.route(g, blocked, place, g.nodes)
    assert got.target == "ex" and got.toward == "w2" and got.arrow is Arrow.AHEAD_RIGHT
    none = routing.routes(g, blocked={"a", "ex"})
    assert guidance.route(g, none, place, g.nodes).kind is Kind.FOLLOW_STAFF


def test_near_entry_points_to_the_next_step():
    g = corridor()
    table = routing.routes(g)
    # right at w2 (whose route leads west via w1 to the assembly point); the display looks west, so people
    # reading it look east and w1 is behind them
    got = guidance.route(g, table, Place(21, 1, facing=270), g.nodes)
    assert got.toward == "w1" and got.target == "a" and got.arrow is Arrow.BACK
    no_assembly = routing.routes(g, blocked={"a"})
    got = guidance.route(g, no_assembly, Place(21, 1, facing=270), g.nodes)
    assert got.toward == "ex" and got.arrow is Arrow.AHEAD
    at_target = guidance.route(g, table, Place(0, -29, facing=None), g.nodes)  # at the assembly point
    assert at_target.toward == "a" and at_target.arrow is None and at_target.target == "a"
    on_spot = guidance.route(g, table, Place(0, -30, facing=0), ["a"])
    assert on_spot.arrow is None


def test_only_points_on_the_screen_floor():
    g = corridor()
    table = routing.routes(g)
    assert guidance.route(g, table, Place(0, 0, 0), []).kind is Kind.FOLLOW_STAFF
    assert guidance.route(g, table, Place(0, 0, 0), ["nope"]).kind is Kind.FOLLOW_STAFF
    assert guidance.route(g, table, Place(30, 0, 0), ["w2", "ex"]).toward in {"w2", "ex"}


@given(st.floats(-100, 100), st.floats(-100, 100), st.floats(0, 359.9),
       st.sets(st.sampled_from(["a", "ex", "w1", "w2"])))
def test_route_properties(x, y, facing, blocked):
    g = corridor()
    table = routing.routes(g, blocked=blocked)
    got = guidance.route(g, table, Place(x, y, facing), g.nodes)
    if not table:
        assert got.kind is Kind.FOLLOW_STAFF
    else:
        # never routes to or through a blocked point
        assert got.kind is Kind.ROUTE and got.target not in blocked and got.toward not in blocked
        assert got.target in {"a", "ex"}
