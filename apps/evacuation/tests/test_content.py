# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage content page and the layout guardrails in the editor and on publish (ADR-0033)."""
import json

from apps.content import layout_format
from apps.content import services as content_services
from apps.content.models import Layout
from apps.core import settings_store
from apps.core.a11y import check_html
from apps.evacuation import content
from apps.evacuation.models import StageContent

URL = "/e/demo/evacuation/content/"


def make_layout(event, admin, elements, name="Evac"):
    lay = Layout.objects.create(event=event, name=name, key=name.lower(), data=layout_format.starter())
    content_services.save_layout(lay, {"format": 1, "width": 1920, "height": 1080, "elements": elements},
                                 actor=admin)
    return lay


GOOD = [{"id": "p", "type": "pictogram", "frame": {"x": 0, "y": 0, "w": 20, "h": 30}, "props": {"code": "arrow"}},
        {"id": "t", "type": "text", "frame": {"x": 0, "y": 40, "w": 90, "h": 20},
         "style": {"fontSize": 10, "color": "#ffffff", "background": "#000000"}, "props": {"text": "{{ evac.text }}"}}]
BAD = [{"id": "t", "type": "text", "frame": {"x": 0, "y": 0, "w": 90, "h": 20},
        "style": {"fontSize": 2, "color": "#333333", "background": "#000000"}, "props": {"text": "Go"}}]


def test_page_and_save(admin_client, event, admin):
    html = admin_client.get(URL).content.decode()
    assert check_html(html) == [] and "Built-in layout" in html and "Leave the building now" in html
    r = admin_client.post(URL, {"state": "evacuate", "layout": "", "texts": "Raus!\nGo now", "rotate_seconds": "5",
                                "sound": "gong", "sound_every": "20", "speech_text": "", "pictograms_only": "on"},
                          follow=True)
    assert "Saved" in r.content.decode()
    row = StageContent.objects.get(event=event, state="evacuate")
    assert row.texts == ["Raus!", "Go now"] and row.sound == "gong" and row.pictograms_only
    admin_client.post(URL, {"state": "attention", "rotate_seconds": "x", "sound": "boom", "sound_every": ""})
    assert StageContent.objects.get(state="attention").sound == "none"
    admin_client.post(URL, {"state": "nonsense"})
    assert StageContent.objects.count() == 2


def test_layout_guardrails(admin_client, event, admin):
    good = make_layout(event, admin, GOOD, "Good")
    bad = make_layout(event, admin, BAD, "Bad")
    r = admin_client.post(URL, {"state": "evacuate", "layout": str(bad.pk), "texts": "", "rotate_seconds": "8",
                                "sound": "siren", "sound_every": "30", "speech_text": ""})
    page = r.content.decode()
    assert r.status_code == 400 and "Not saved" in page and "safety sign" in page
    assert not StageContent.objects.exists()
    r = admin_client.post(URL, {"state": "evacuate", "layout": str(good.pk), "texts": "", "rotate_seconds": "8",
                                "sound": "siren", "sound_every": "30", "speech_text": ""}, follow=True)
    assert "Saved" in r.content.decode() and StageContent.objects.get().layout_id == good.pk
    # once used for evacuation, the editor reports the guardrails and publishing a failing draft is refused
    content_services.save_layout(good, {"format": 1, "width": 1920, "height": 1080, "elements": BAD}, actor=admin,
                                 expected_version=good.version)
    findings = content_services.layout_findings(good)
    assert any(f["level"] == "error" and f["message"].startswith("Evacuation") for f in findings)
    r = admin_client.post(f"/e/demo/content/layouts/{good.pk}/publish/")
    assert r.status_code == 400 and r.json()["errors"]
    page = admin_client.get(f"/e/demo/content/layouts/{good.pk}/edit/").content.decode()
    assert '"findings": [{"level": "error"' in page
    save = admin_client.post(f"/e/demo/content/layouts/{good.pk}/save/",
                             json.dumps({"data": {"format": 1, "width": 1920, "height": 1080, "elements": GOOD},
                                         "version": good.version + 0}), content_type="application/json")
    good.refresh_from_db()
    assert save.json()["ok"] and [f for f in save.json()["findings"] if f["level"] == "error"] == []
    assert admin_client.post(f"/e/demo/content/layouts/{good.pk}/publish/").status_code == 200
    html = admin_client.get(URL).content.decode()
    assert check_html(html) == [] and "Good" in html
    # layouts of other events or unused ones are not checked
    assert content.layout_check(bad, bad.data) == []
    from apps.core import modules

    modules.set_event(event, "evacuation", False)
    assert content.layout_check(good, BAD and {"elements": BAD}) == []


def test_scheduled_publish_refused(event, admin):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.models import AuditLog

    # fine for the staged model when scheduled; the zones model (set before it is due) needs a direction
    settings_store.save("evacuation", "instance", "", {"model": "staged"})
    plain = [GOOD[1], {"id": "p", "type": "pictogram", "frame": {"x": 0, "y": 0, "w": 9, "h": 9},
                       "props": {"code": "E002"}}]
    lay = make_layout(event, admin, plain, "Sched")
    StageContent.objects.create(event=event, state="evacuate", layout_id=lay.pk)
    content_services.publish_layout(lay, actor=admin, at=timezone.now() + timedelta(seconds=1))
    settings_store.save("evacuation", "instance", "", {"model": "zones"})
    assert content_services.publish_due(timezone.now() + timedelta(seconds=5)) == 0
    assert AuditLog.objects.filter(action="layout.publish_refused").exists()


def test_zones_model_needs_a_direction(event, admin):
    settings_store.save("evacuation", "instance", "", {"model": "staged"})
    no_dir = [GOOD[1], {"id": "p", "type": "pictogram", "frame": {"x": 0, "y": 0, "w": 9, "h": 9},
                        "props": {"code": "E002"}}]
    lay = make_layout(event, admin, no_dir, "Plain")
    assert [f for f in content.findings(event, lay, lay.data) if f.level == "error"] == []
    settings_store.save("evacuation", "instance", "", {"model": "zones"})
    assert [f.code for f in content.findings(event, lay, lay.data) if f.level == "error"] == ["direction"]
