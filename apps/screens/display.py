# SPDX-License-Identifier: AGPL-3.0-or-later
"""Per-screen display settings (namespace ``display``): instance -> event -> screen groups -> screen.

The player applies them itself (rotation, overscan, scale, keystone, dimming and sleep times, audio, a daily
reload). A screen in several groups takes the groups in name order; a later group wins over an earlier one.
"""
from __future__ import annotations

from typing import Any

from apps.core import settings_schema, settings_store

HHMM = {"type": "string", "pattern": r"^(|([01][0-9]|2[0-3]):[0-5][0-9])$", "maxLength": 5}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rotation": {"type": "string", "enum": ["0", "90", "180", "270"], "default": "0",
                     "x-enum-labels": ["0°", "90° (portrait, clockwise)", "180°", "270° (portrait, anticlockwise)"],
                     "title": "Rotation",
                     "description": "For displays mounted rotated when the operating system cannot rotate them."},
        "overscan": {"type": "integer", "minimum": 0, "maximum": 15, "default": 0, "title": "Overscan (% per edge)",
                     "description": "Shrinks the picture for TVs that cut off the edges."},
        "scale": {"type": "integer", "minimum": 50, "maximum": 200, "default": 100, "title": "Content scale (%)"},
        "keystone_x": {"type": "number", "minimum": -20, "maximum": 20, "default": 0,
                       "title": "Keystone, horizontal (degrees)", "description": "Projectors mounted off-centre."},
        "keystone_y": {"type": "number", "minimum": -20, "maximum": 20, "default": 0,
                       "title": "Keystone, vertical (degrees)"},
        "wall_columns": {"type": "integer", "minimum": 1, "maximum": 8, "default": 1, "title": "Video wall: columns",
                         "description": "Several displays showing one layout together. Set columns and rows on "
                                        "the wall's screen group, the position on each screen. Alarms show "
                                        "complete on every display."},
        "wall_rows": {"type": "integer", "minimum": 1, "maximum": 8, "default": 1, "title": "Video wall: rows"},
        "wall_column": {"type": "integer", "minimum": 1, "maximum": 8, "default": 1,
                        "title": "Video wall: this display's column", "description": "1 = left."},
        "wall_row": {"type": "integer", "minimum": 1, "maximum": 8, "default": 1,
                     "title": "Video wall: this display's row", "description": "1 = top."},
        "wall_bezel": {"type": "number", "minimum": 0, "maximum": 10, "default": 0,
                       "title": "Video wall: gap between displays (% of a display)",
                       "description": "Frame width between two pictures, so lines continue straight across."},
        "expected_resolution": {"type": "string", "pattern": r"^(|\d{3,5}x\d{3,5})$", "maxLength": 11,
                                "default": "", "title": "Expected resolution",
                                "description": "e.g. 1920x1080. The screen page warns when the screen reports "
                                               "a different one."},
        "dim_from": {**HHMM, "default": "", "title": "Dim from (HH:MM)"},
        "dim_until": {**HHMM, "default": "", "title": "Dim until (HH:MM)"},
        "dim_level": {"type": "integer", "minimum": 10, "maximum": 90, "default": 40,
                      "title": "Brightness when dimmed (%)"},
        "sleep_from": {**HHMM, "default": "", "title": "Screen off from (HH:MM)",
                       "description": "Shows black (kiosks also switch the display off). Evacuation always "
                                      "wakes the screen (phase 3)."},
        "sleep_until": {**HHMM, "default": "", "title": "Screen off until (HH:MM)"},
        "audio": {"type": "boolean", "default": True, "title": "Play sound",
                  "description": "Off mutes every video and audio widget on this screen."},
        "volume": {"type": "integer", "minimum": 0, "maximum": 100, "default": 80, "title": "Volume (%)"},
        "reduce_motion": {"type": "boolean", "default": False, "title": "Reduce motion",
                          "description": "No slide transitions or entrance effects (as when the device asks for "
                                         "reduced motion). Slide timers still count down, in steps. Alarms and "
                                         "announcements always appear at once."},
        "daily_reload": {**HHMM, "default": "04:00", "title": "Daily reload at (HH:MM)",
                         "description": "Reloads the player once a day to free memory. Empty: never."},
        "evacuation_role": {"type": "string", "enum": ["participant", "info", "excluded"], "default": "participant",
                            "x-enum-labels": ["Takes part in evacuation", "Shows evacuation information only",
                                              "Excluded (e.g. backstage monitor)"],
                            "title": "Evacuation role",
                            "description": "Used by the evacuation module (phase 3)."},
    },
}


def groups_in_order(screen) -> list:
    return sorted(screen.groups(), key=lambda g: (g.name.lower(), str(g.pk)))


def resolve(screen=None, *, group=None, event=None) -> settings_schema.Resolved:
    """Resolved display settings of a screen (or of a group, for its settings page)."""
    if screen is not None:
        return settings_store.resolve("display", event=screen.event, screen_groups=groups_in_order(screen),
                                      screen=screen)
    if group is not None:
        return settings_store.resolve("display", event=group.event, screen_group=group)
    return settings_store.resolve("display", event=event)


def for_screen(screen) -> dict[str, Any]:
    return resolve(screen).values
