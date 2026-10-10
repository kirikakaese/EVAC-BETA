# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evacuation layout guardrails (ADR-0033)."""
import pytest

from apps.evacuation import lint

TOKENS = {"mode": "dark", "dark_background": "#000000", "dark_text": "#ffffff", "dark_primary": "#4f8cff"}


def layout(*elements, bg=None):
    data = {"format": 1, "width": 1920, "height": 1080, "elements": list(elements)}
    if bg is not None:
        data["background"] = bg
    return data


def el(eid, type_, style=None, props=None, frame=None, hidden=False):
    e = {"id": eid, "type": type_, "frame": frame or {"x": 0, "y": 0, "w": 50, "h": 20}, "style": style or {},
         "props": props or {}}
    if hidden:
        e["hidden"] = True
    return e


def codes(found):
    return sorted((f.level, f.code) for f in found)


def test_required_elements():
    assert codes(lint.lint(layout(), zones_model=False)) == [("error", "pictogram"), ("error", "text")]
    good = layout(el("p", "pictogram", props={"code": "E002"}), el("t", "text", {"fontSize": 10}, {"text": "Go"}))
    assert lint.lint(good, zones_model=False, tokens=TOKENS) == []
    assert codes(lint.lint(good, zones_model=True, tokens=TOKENS)) == [("error", "direction")]
    arrow = layout(el("p", "pictogram", props={"code": "arrow"}), el("t", "text", {"fontSize": 10}, {"text": "Go"}))
    assert lint.lint(arrow, zones_model=True, tokens=TOKENS) == []
    by_text = layout(el("p", "pictogram"), el("t", "text", {"fontSize": 10}, {"text": "To {{ evac.direction }}"}))
    assert lint.lint(by_text, zones_model=True, tokens=TOKENS) == []
    hidden = layout(el("p", "pictogram", hidden=True), el("t", "text", {"fontSize": 10}, {"text": "x"}))
    assert ("error", "pictogram") in codes(lint.lint(hidden, zones_model=False, tokens=TOKENS))


@pytest.mark.parametrize(("fg", "bg", "expected"), [
    ("#ffffff", "#000000", []), ("#777777", "#000000", [("warning", "contrast")]),
    ("#444444", "#000000", [("error", "contrast")]), ("token:text", "token:background", []),
])
def test_contrast(fg, bg, expected):
    data = layout(el("p", "pictogram"), el("t", "text", {"color": fg, "background": bg, "fontSize": 10}))
    assert codes(lint.lint(data, zones_model=False, tokens=TOKENS)) == expected


def test_contrast_behind_shape_and_image():
    shape = el("s", "shape", {"background": "#ffffff"}, frame={"x": 0, "y": 0, "w": 100, "h": 100})
    text = el("t", "text", {"color": "#eeeeee", "fontSize": 10})
    assert codes(lint.lint(layout(el("p", "pictogram"), shape, text), zones_model=False, tokens=TOKENS)) == [
        ("error", "contrast")]
    away = el("s", "shape", {"background": "#ffffff"}, frame={"x": 80, "y": 80, "w": 10, "h": 10})
    assert lint.lint(layout(el("p", "pictogram"), away, text), zones_model=False, tokens=TOKENS) == []
    img = layout(el("p", "pictogram"), text, bg={"asset": "x"})
    assert codes(lint.lint(img, zones_model=False, tokens=TOKENS)) == [("warning", "contrast_unknown")]
    assert lint.contrast("#zzzzzz", "#000000") is None and lint.resolve("token:missing", {}, "") is None
    assert lint.resolve("transparent", TOKENS, "") is None and lint.resolve("", TOKENS, "#123456") == "#123456"
    bad = layout(el("p", "pictogram"), el("t", "text", {"fontSize": 10}), el("x", "shape", frame={"x": "a"}))
    assert lint.lint(bad, zones_model=False, tokens=TOKENS) == []


def test_text_size():
    assert lint.min_font_size(8, 0.6) == pytest.approx(7.6, abs=0.1)
    small = layout(el("p", "pictogram"), el("t", "text", {"fontSize": 5}))
    tiny = layout(el("p", "pictogram"), el("t", "text", {"fontSize": 3}))
    fit = layout(el("p", "pictogram"), el("t", "text", {"fontSize": 2}, {"autofit": True}))
    assert codes(lint.lint(small, zones_model=False, tokens=TOKENS)) == [("warning", "size")]
    assert codes(lint.lint(tiny, zones_model=False, tokens=TOKENS)) == [("error", "size")]
    assert lint.lint(fit, zones_model=False, tokens=TOKENS) == []
    near = lint.lint(tiny, zones_model=False, tokens=TOKENS, viewing_distance_m=2)
    assert near == []
    assert lint.Finding("error", "x", "m").as_dict()["level"] == "error"
