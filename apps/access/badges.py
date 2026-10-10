# SPDX-License-Identifier: AGPL-3.0-or-later
"""Badges and wristband labels (ADR-0044): a ticket type's badge is a layout of the layout editor with a badge
sized canvas; ``{{ attendee.name }}``, ``{{ attendee.company }}``, ``{{ ticket.name }}`` and a QR element with
``{{ attendee.code }}`` are filled per attendee by the shared renderer on a print page. Without a layout the
built-in badge (name, organisation, ticket type, QR code) is used."""
from __future__ import annotations

from typing import Any

from django.utils.text import slugify
from django.utils.translation import gettext as _

from .models import Attendee, TicketType

#: A6 portrait (105 × 148 mm) at 250 dpi
BADGE_SIZE = (1033, 1457)


def starter(colour: str) -> dict[str, Any]:
    from apps.content import layout_format as lf

    w, h = BADGE_SIZE
    return {"format": lf.FORMAT, "width": w, "height": h, "elements": [
        {"id": "page", "type": "shape", "name": "Paper", "frame": {"x": 0, "y": 0, "w": 100, "h": 100},
         "style": {"background": "#ffffff"}, "props": {"shape": "rect"}, "locked": True},
        {"id": "band", "type": "shape", "name": "Colour band", "frame": {"x": 0, "y": 0, "w": 100, "h": 14},
         "style": {"background": colour}, "props": {"shape": "rect"}},
        {"id": "event", "type": "text", "name": "Event", "frame": {"x": 6, "y": 2, "w": 88, "h": 10},
         "style": {"fontFamily": "token:heading", "fontSize": 4.2, "fontWeight": 700, "color": "#ffffff",
                   "textAlign": "center", "verticalAlign": "middle"},
         "props": {"text": "{{ event.name }}", "autofit": True}},
        {"id": "name", "type": "text", "name": "Name", "frame": {"x": 6, "y": 20, "w": 88, "h": 16},
         "style": {"fontFamily": "token:heading", "fontSize": 7, "fontWeight": 700, "color": "#111111",
                   "textAlign": "center", "verticalAlign": "middle"},
         "props": {"text": '{{ attendee.name|default:"Ada Lovelace" }}', "autofit": True}},
        {"id": "company", "type": "text", "name": "Organisation", "frame": {"x": 6, "y": 37, "w": 88, "h": 7},
         "style": {"fontSize": 3.4, "color": "#333333", "textAlign": "center"},
         "props": {"text": "{{ attendee.company }}", "autofit": True}},
        {"id": "qr", "type": "qr", "name": "Ticket QR code", "frame": {"x": 25, "y": 48, "w": 50, "h": 35},
         "style": {"background": "#ffffff"}, "props": {"text": '{{ attendee.code|default:"EVAC" }}'}},
        {"id": "ticket", "type": "text", "name": "Ticket type", "frame": {"x": 0, "y": 88, "w": 100, "h": 12},
         "style": {"fontSize": 4.6, "fontWeight": 700, "color": "#ffffff", "background": colour,
                   "textAlign": "center", "verticalAlign": "middle"},
         "props": {"text": '{{ ticket.name|default:"Day ticket"|upper }}', "autofit": True}},
    ]}


def create_layout(t: TicketType, *, actor: Any, request: Any = None) -> Any:
    """A badge layout for ``t`` to edit in the layout editor (never the event's default screen layout)."""
    from apps.content import services as content
    from apps.content.models import Layout

    base = f"badge-{slugify(t.name)[:40] or 'ticket'}"
    key, n = base, 1
    while Layout.objects.filter(event=t.event, key=key).exists():
        n += 1
        key = f"{base}-{n}"
    layout = content.create_layout(t.event, name=_("Badge: %(t)s") % {"t": t.name}, key=key, actor=actor,
                                   request=request, data=starter(t.colour))
    if layout.is_default:
        Layout.objects.filter(pk=layout.pk).update(is_default=False)
        layout.is_default = False
    t.badge_layout = layout
    t.save(update_fields=["badge_layout"])
    return layout


def page_vars(a: Attendee) -> dict[str, Any]:
    zones = ", ".join(z.name for z in a.ticket_type.zones.all())
    return {"attendee": {"name": a.name, "company": a.company, "code": a.code, "email": a.email, "zones": zones},
            "ticket": {"name": a.ticket_type.name, "colour": a.ticket_type.colour}}


def sheet_config(event: Any, layout: Any, attendees: list[Attendee]) -> dict[str, Any]:
    """Data for the preview island's print sheet (``[data-preview-pages]``)."""
    from apps.content import files as content_files
    from apps.content import services as content
    from apps.content import tokens as tok
    from apps.content.models import Asset, owner_q

    theme = layout.theme or content.event_theme(event)
    values = content.resolved_tokens(theme)
    assets = Asset.objects.filter(owner_q(event), status=Asset.Status.READY)
    images = {str(a.pk): content_files.asset_url(a, a.variant("webp", "original"))
              for a in assets if str(a.pk) in tok.referenced_assets(values)}
    fonts = content.font_stacks(event)
    from django.utils import timezone

    return {"layout": layout.data, "at": int(timezone.now().timestamp() * 1000), "timezone": event.timezone,
            "vars": {"event": {"name": event.name, "slug": event.slug}},
            "pages": [page_vars(a) for a in attendees],
            "pageLabels": [_("Badge of %(n)s") % {"n": a.name} for a in attendees],
            "assets": {str(a.pk): content.asset_entry(a, content_files.portal_url) for a in assets},
            "fonts": fonts, "themeVariables": tok.css_variables(values, families=fonts, urls=images)}
