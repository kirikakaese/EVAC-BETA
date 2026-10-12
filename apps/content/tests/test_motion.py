# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screen motion in the layout format and the display settings (ADR-0051)."""
import pytest
from rest_framework.test import APIClient

from apps.content import layout_format, services
from apps.core import settings_store
from apps.screens import display
from apps.screens import services as screen_services
from conftest import login_2fa

FRAME = {"x": 0, "y": 98, "w": 100, "h": 2}


def layout(*elements):
    return {**layout_format.empty(), "elements": list(elements)}


def test_slide_timer_and_entrance_effects_validate():
    timer = {"id": "timer", "type": "progress", "frame": FRAME, "style": {"color": "token:accent",
                                                                          "background": "token:surface"},
             "props": {"orientation": "vertical", "mode": "grow", "reverse": True, "untimed": "hide"}}
    animated = {"id": "t", "type": "text", "frame": FRAME, "props": {"text": "Hi"},
                "animation": {"enter": "slide-left", "duration": 800, "delay": 1500}}
    assert layout_format.validate(layout(timer, animated)) == []
    assert layout_format.validate(layout({"id": "bare", "type": "progress", "frame": FRAME})) == []
    for broken in [
        {**timer, "props": {"orientation": "diagonal"}},
        {**timer, "props": {"mode": "bounce"}},
        {**timer, "props": {"untimed": "blink"}},
        {**timer, "props": {"seconds": 10}},  # the duration comes from the playlist, not the element
        {**animated, "animation": {"enter": "spin"}},
        {**animated, "animation": {"enter": "fade", "duration": 10_001}},
        {**animated, "animation": {"enter": "fade", "delay": 60_001}},
        {**animated, "animation": {"enter": "fade", "duration": -1}},
        {**animated, "animation": {"enter": "fade", "easing": "linear"}},
    ]:
        assert layout_format.validate(layout(broken)), broken


@pytest.mark.django_db
def test_editor_offers_the_slide_timer(client, admin, event):
    lay = services.create_layout(event, name="Foyer", key="foyer", actor=admin)
    login_2fa(client, admin)
    page = client.get(f"/e/demo/content/layouts/{lay.pk}/edit/").content.decode()
    assert '"progress"' in page and "Slide timer" in page and "Play animations" in page


@pytest.mark.django_db
def test_reduce_motion_display_setting_reaches_the_screen(client, admin, event):
    data = client.post("/player/api/pair/", data="{}", content_type="application/json").json()
    screen = screen_services.pair(event, data["code"], actor=admin, name="Foyer")
    token = client.post(f"/player/api/pair/{data['id']}/", HTTP_X_PAIRING_SECRET=data["secret"]).json()["token"]
    device = APIClient()
    device.credentials(HTTP_AUTHORIZATION=f"Screen {token}")
    assert display.SCHEMA["properties"]["reduce_motion"]["default"] is False
    assert device.get("/player/api/config/").json()["display"]["reduce_motion"] is False
    settings_store.save("display", "screen", str(screen.pk), {"reduce_motion": True}, user=admin, event=event)
    assert device.get("/player/api/config/").json()["display"]["reduce_motion"] is True
