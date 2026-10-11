# SPDX-License-Identifier: AGPL-3.0-or-later
"""Template gallery (roadmap 9.3, ADR-0046): ready-made layouts registered with ``r.layout_template(...)``.

The content module registers the general ones below; other modules add their own (the program module its stage
screens). "Use template" copies the template's data into a new layout of the event, which is then edited and
published like any other. Templates use theme tokens and template variables only, so they fit every event.
"""
from __future__ import annotations

from typing import Any

from django.utils.translation import gettext_lazy as _

from apps.core import modules
from apps.core.plugins import LayoutTemplateSpec
from apps.core.registry import Registry, registry

from .layout_format import FORMAT

Frame = tuple[float, float, float, float]
HEADING = {"fontFamily": "token:heading", "fontWeight": 800}
CARD = {"background": "token:surface", "radius": 2, "padding": 3, "shadow": True}
CENTER = {"textAlign": "center"}


def layout(elements: list[dict[str, Any]], *, width: int = 1920, height: int = 1080,
           background: str = "token:background") -> dict[str, Any]:
    """Layout data for a template (format 1)."""
    return {"format": FORMAT, "width": width, "height": height, "background": {"color": background},
            "elements": elements}


def element(id_: str, type_: str, frame: Frame, props: dict[str, Any] | None = None, **style: Any) -> dict[str, Any]:
    x, y, w, h = frame
    return {"id": id_, "type": type_, "name": id_.replace("-", " ").capitalize(),
            "frame": {"x": x, "y": y, "w": w, "h": h}, "style": style, "props": props or {}}


def text(id_: str, value: str, frame: Frame, **style: Any) -> dict[str, Any]:
    return element(id_, "text", frame, {"text": value, "autofit": True}, **style)


def welcome() -> dict[str, Any]:
    return layout([
        text("kicker", "Welcome to", (8, 18, 84, 8), fontSize=4.5, color="token:accent", textTransform="uppercase",
             letterSpacing=0.15, fontWeight=700, **CENTER),
        text("title", "{{ event.name }}", (8, 27, 84, 24), fontSize=13, **HEADING, **CENTER),
        text("message", "Enjoy the event!", (14, 56, 72, 10), fontSize=4.5, color="token:muted", **CENTER),
        element("clock", "clock", (36, 74, 28, 14), {"format": "HH:mm"}, fontSize=10, tabularNumbers=True,
                **CENTER),
    ])


def info_board() -> dict[str, Any]:
    return layout([
        text("title", "{{ event.name }}", (5, 6, 62, 12), fontSize=7, color="token:accent", **HEADING),
        element("date", "date", (68, 6, 27, 6), {"format": "weekday"}, fontSize=3.5, color="token:muted",
                textAlign="right"),
        element("clock", "clock", (68, 11, 27, 8), {"format": "HH:mm"}, fontSize=6, textAlign="right",
                tabularNumbers=True),
        element("info", "richtext", (5, 24, 58, 66), {"text": "**Info point** at the main entrance\n\n"
                                                      "**First aid** next to the info point\n\n"
                                                      "**Lost & found** at the info point"},
                fontSize=4, **CARD),
        element("qr", "qr", (69, 26, 26, 44), {"text": "https://example.org"}, background="#ffffff", padding=2,
                radius=2),
        text("qr-caption", "Scan for the full program", (67, 72, 30, 8), fontSize=3, color="token:muted", **CENTER),
    ])


def portrait_info() -> dict[str, Any]:
    return layout([
        text("title", "{{ event.name }}", (6, 5, 88, 10), fontSize=4.5, color="token:accent", **HEADING),
        element("clock", "clock", (6, 16, 88, 9), {"format": "HH:mm"}, fontSize=5.5, tabularNumbers=True),
        element("date", "date", (6, 25, 88, 4), {"format": "long"}, fontSize=2.2, color="token:muted"),
        element("body", "richtext", (6, 33, 88, 52), {"text": "**Today**\n\nDoors open 10:00\n\nTalks from 11:00"},
                fontSize=2.6, **CARD),
        text("footer", "{{ screen.zone }}", (6, 89, 88, 5), fontSize=2, color="token:muted", **CENTER),
    ], width=1080, height=1920)


def countdown() -> dict[str, Any]:
    return layout([
        text("kicker", "Starting in", (10, 18, 80, 10), fontSize=5, color="token:muted", textTransform="uppercase",
             letterSpacing=0.12, **CENTER),
        element("countdown", "countdown", (10, 30, 80, 32), {"target": "", "format": "auto",
                                                             "finished": "Now!"},
                fontSize=18, tabularNumbers=True, **HEADING, **CENTER),
        text("what", "{{ event.name }}", (10, 68, 80, 12), fontSize=5, color="token:accent", **CENTER),
    ])


def sponsors() -> dict[str, Any]:
    return layout([
        text("title", "Thanks to our sponsors", (5, 5, 90, 12), fontSize=6, **HEADING, **CENTER),
        element("logos", "slideshow", (10, 22, 80, 64), {"assets": [], "interval": 8, "fit": "contain"}, **CARD),
        text("footer", "{{ event.name }}", (5, 89, 90, 6), fontSize=3, color="token:muted", **CENTER),
    ])


def wayfinding() -> dict[str, Any]:
    rows = []
    for i, (arrow, label) in enumerate([("left", "Main stage"), ("ahead", "Food court"), ("right", "Toilets")]):
        y = 20 + i * 25
        rows += [element(f"arrow-{i + 1}", "pictogram", (8, y, 16, 20), {"code": "arrow", "direction": arrow}),
                 text(f"place-{i + 1}", label, (28, y + 2, 64, 16), fontSize=8, fontWeight=700)]
    return layout([text("title", "{{ screen.zone }}", (8, 5, 84, 10), fontSize=5, color="token:muted"), *rows])


def media_ticker() -> dict[str, Any]:
    return layout([
        element("media", "image", (0, 0, 100, 84), {"asset": "", "fit": "cover"}),
        element("bar", "shape", (0, 84, 100, 16), {"shape": "rect"}, background="token:primary"),
        element("clock", "clock", (86, 86, 12, 12), {"format": "HH:mm"}, fontSize=5, color="#ffffff",
                tabularNumbers=True, textAlign="right"),
        element("ticker", "text", (2, 86, 82, 12), {"text": "Welcome to {{ event.name }} · Follow the signs to the "
                                                    "main stage · Water refill at the info point",
                                                    "marquee": True}, fontSize=5, color="#ffffff"),
    ])


BUILTIN = [
    ("welcome", _("Welcome"), _("Event name, a short message and the time."), _("General"), welcome),
    ("info-board", _("Information board"), _("Where to find what, with a QR code and the time."), _("General"),
     info_board),
    ("portrait-info", _("Portrait information"), _("For screens mounted upright: time, date and notes."),
     _("General"), portrait_info),
    ("countdown", _("Countdown"), _("Counts down to the start of something."), _("General"), countdown),
    ("sponsors", _("Sponsor slideshow"), _("Logos from the asset library in turn."), _("Media"), sponsors),
    ("media-ticker", _("Picture with ticker"), _("A full-width picture with a scrolling news line."), _("Media"),
     media_ticker),
    ("wayfinding", _("Wayfinding"), _("Arrows to the main places, per screen zone."), _("Wayfinding"),
     wayfinding),
]


def register(r: Registry) -> None:
    for order, (key, name, description, category, fn) in enumerate(BUILTIN):
        r.layout_template(LayoutTemplateSpec(key=key, name=str(name), description=str(description),
                                             category=str(category), data=fn, module="content", order=order * 10))


def available(event) -> list[LayoutTemplateSpec]:
    """Templates usable in ``event`` (their module on), in gallery order."""
    specs = registry.ensure_loaded().layout_templates.values()
    return sorted((s for s in specs if s.module == "core" or modules.is_enabled(s.module, event)),
                  key=lambda s: (s.order, s.name))


def get(event, key: str) -> LayoutTemplateSpec | None:
    return next((s for s in available(event) if s.key == key), None)
