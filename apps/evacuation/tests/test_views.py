# SPDX-License-Identifier: AGPL-3.0-or-later
"""Control page: module switch, hold-to-confirm form, permissions, history (ADR-0029)."""
from apps.core import modules
from apps.core.a11y import check_html
from apps.evacuation import services
from apps.evacuation.models import EvacState, StateChange
from conftest import login_2fa

from .conftest import tf

URL = "/e/demo/evacuation/"


def page(client, url=URL):
    r = client.get(url)
    assert r.status_code == 200, r.status_code
    html = r.content.decode()
    assert check_html(html) == []
    return html


def test_module_switch(admin_client, event):
    assert admin_client.get(URL).status_code == 200
    modules.set_instance("evacuation", False)
    assert admin_client.get(URL).status_code == 404
    assert admin_client.post(f"{URL}change/", {"scope": "event", "state": "evacuate"}).status_code == 404
    modules.set_instance("evacuation", True)
    modules.set_event(event, "evacuation", False)
    assert admin_client.get(URL).status_code == 404


def test_control_page_flow(admin_client, event, zones):
    html = page(admin_client)
    assert "not a certified fire alarm" in html and 'data-hold="1500"' in html and "Whole event" in html
    north = zones["North"]
    r = admin_client.post(f"{URL}change/", {"scope": str(north.pk), "state": "evacuate", "reason": "fire"})
    assert r.status_code == 302
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "attention"})
    html = page(admin_client)
    assert "badge-evac-evacuate" in html and "badge-evac-attention" in html and "fire" in html
    # all clear lists the zone in alarm, ticked by default
    assert f'value="{north.pk}"' in html and "checked" in html
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "all_clear"})  # unticked: keep North
    assert r.status_code == 302
    assert EvacState.objects.get(zone=north).state == "evacuate"
    html = page(admin_client)
    assert "Back to normal now" in html
    assert admin_client.post(f"{URL}end-all-clear/").status_code == 302
    assert EvacState.objects.get(event=event, zone=None).state == "normal"
    # the zone gets its own all clear and early end
    admin_client.post(f"{URL}change/", {"scope": str(north.pk), "state": "all_clear"})
    admin_client.post(f"{URL}end-all-clear/", {"zone": str(north.pk)})
    assert EvacState.objects.get(zone=north).state == "normal"
    for bad in ("nope", "00000000-0000-0000-0000-000000000000"):
        r = admin_client.post(f"{URL}end-all-clear/", {"zone": bad}, follow=True)
        assert "Unknown zone" in r.content.decode()
    r = admin_client.post(f"{URL}end-all-clear/", follow=True)
    assert "Already normal" in r.content.decode()


def test_refusals_show_on_the_form(admin_client, event):
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "all_clear"})
    assert r.status_code == 400 and "no alarm to clear" in r.content.decode()
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "bogus"})
    assert r.status_code == 400
    admin_client.post(f"{URL}change/", {"scope": "event", "state": "evacuate"})
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "attention", "drill": "on"})
    assert r.status_code == 400 and "drills cannot start" in r.content.decode()


def test_drill_marker(admin_client, event):
    r = admin_client.post(f"{URL}change/", {"scope": "event", "state": "evacuate", "drill": "on"}, follow=True)
    html = r.content.decode()
    assert "badge-evac-drill" in html and "DRILL" in html
    assert StateChange.objects.get().drill
    assert "badge-evac-drill" in page(admin_client, f"{URL}history/?drills=only")
    assert "No changes yet" in page(admin_client, f"{URL}history/?drills=none")
    assert "evacuate" in page(admin_client, f"{URL}history/").lower()


def test_viewer_sees_but_cannot_change(client, event, member):
    login_2fa(client, member)
    html = page(client)
    assert "Hold to confirm" not in html
    assert client.post(f"{URL}change/", {"scope": "event", "state": "evacuate"}).status_code == 403


def test_permission_denied_in_scope(client, event, role, zones):
    from apps.accounts.models import User
    from apps.events import services as event_services

    u = User.objects.create_user(email="n@example.org", password="pw-12345678x")
    north = zones["North"]
    event_services.assign_role(event, u, role("control-room"), scope_kind="zone", scope_id=str(north.pk),
                               scope_label="North")
    login_2fa(client, u)
    r = client.post(f"{URL}change/", {"scope": "event", "state": "evacuate"})
    assert r.status_code == 400 and "may not make this change" in r.content.decode()
    assert client.post(f"{URL}change/", {"scope": str(north.pk), "state": "evacuate"}).status_code == 302
    services.change(event, "attention", actor=None, source="test")
    assert services.effective_for(event, [str(north.pk)]).state.value == "evacuate"
    assert tf(u).user == u
