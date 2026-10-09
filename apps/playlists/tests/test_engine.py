# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Python engine against the vectors shared with frontend/src/program/engine.ts."""
import json
from pathlib import Path

import pytest
from django.conf import settings

from apps.playlists import engine

VECTORS = json.loads((Path(settings.BASE_DIR) / "frontend/test/fixtures/program-vectors.json").read_text())


def _program(variant):
    p = VECTORS["program"]
    if variant == "no-urgent":
        return {**p, "entries": [e for e in p["entries"] if e["id"] != "override:o2"]}
    return p


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: f"{c['ctx']}-{c['t']}-{c['variant']}")
def test_vectors(case):
    program = _program(case["variant"])
    slide = engine.slide_at(program, VECTORS["contexts"][case["ctx"]], case["t"])
    assert slide == case["slide"]
    assert engine.next_change(program, case["t"], slide) == case["next"]


def test_units():
    u = VECTORS["units"]
    assert {s: engine.fnv1a(s) for s in u["fnv"]} == u["fnv"]
    assert {k: engine.shuffled(list(range(8)), int(k)) for k in u["shuffle"]} == u["shuffle"]
    assert engine.weighted(["a", "b", "c"], [3, 1, 2]) == u["weighted"]


def test_conditions():
    ctx = {"screen": {"zone": "North", "tags": ["a"], "room": ""}, "n": 3, "flag": True}
    assert engine.condition("", ctx)
    assert engine.condition('screen.zone == "North"', ctx)
    assert engine.condition("screen.zone|lower == 'north'", ctx)
    assert engine.condition("screen.zone|upper != 'north'", ctx)
    assert not engine.condition("screen.room", ctx)
    assert engine.condition("not screen.room", ctx)
    assert engine.condition("{{ screen.tags }}", ctx)
    assert engine.condition('screen.room|default:"x" == "x"', ctx)
    assert engine.condition('screen.tags|join:"+" == "a"', ctx)
    assert engine.condition("n == 3", ctx) and engine.condition("3 == 3.0", ctx)
    assert engine.condition('flag == "true"', ctx)
    assert not engine.condition("screen.zone.name", ctx)
    assert engine.condition("screen|truncate:2", ctx)  # unknown filters pass the value on


def test_shuffle_changes_per_cycle_and_is_stable():
    program = VECTORS["program"]
    ctx = VECTORS["contexts"]["plain"]
    a = [s["layout"] for s in engine.flatten(program, "P2", ctx, 0, 1)]
    assert a == [s["layout"] for s in engine.flatten(program, "P2", ctx, 0, 1)]
    orders = {tuple(s["layout"] for s in engine.flatten(program, "P2", ctx, 0, k)) for k in range(10)}
    assert len(orders) > 1
    assert sorted(a) == ["L1", "L2", "L3", "L4"]


def test_empty_program():
    assert engine.slide_at({"entries": []}, {}, 0) is None
    assert engine.next_change({"entries": []}, 0, None) is None
    p = {"entries": [{"id": "x", "source": "default", "name": "", "priority": 0, "content": {"playlist": "nope"},
                      "windows": [[None, None]]}], "playlists": {}, "layouts": {}}
    assert engine.slide_at(p, {}, 5) is None
