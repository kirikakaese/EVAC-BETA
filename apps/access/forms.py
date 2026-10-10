# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import AccessZone, Attendee, TicketType


class AttendeeForm(forms.ModelForm):
    class Meta:
        model = Attendee
        fields = ["name", "email", "company", "ticket_type", "code", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["ticket_type"].queryset = TicketType.objects.filter(event=event)
        self.fields["code"].required = False


class TicketTypeForm(forms.ModelForm):
    class Meta:
        model = TicketType
        fields = ["name", "colour", "zones", "badge_layout", "order"]
        widgets = {"colour": forms.TextInput(attrs={"type": "color"}), "zones": forms.CheckboxSelectMultiple}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.content.models import Layout

        self.fields["zones"].queryset = AccessZone.objects.filter(event=event)
        self.fields["badge_layout"].queryset = Layout.objects.filter(event=event)


class ZoneForm(forms.ModelForm):
    area_id = forms.TypedChoiceField(label=_("Occupancy area"), required=False, coerce=str, empty_value=None,
                                     help_text=_("Scans in and out count people in this area (module Occupancy)."))

    class Meta:
        model = AccessZone
        fields = ["name", "open_to_all", "checkin", "reentry", "room", "area_id", "order"]

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.venues.models import Room

        self.fields["room"].queryset = Room.objects.filter(venue__in=event.venues.all())
        self.fields["area_id"].choices = [("", "–"), *area_choices(event)]
        if self.instance.area_id:
            self.initial["area_id"] = str(self.instance.area_id)


def area_choices(event: Any) -> list[tuple[str, str]]:
    from django.apps import apps

    from apps.core import modules

    if not apps.is_installed("apps.crowd") or not modules.is_enabled("crowd", event):
        return []
    from apps.crowd.models import Area

    return [(str(a.pk), a.name) for a in Area.objects.filter(event=event)]


class ImportForm(forms.Form):
    file = forms.FileField(label=_("CSV file"), help_text=_("Columns: name, ticket_type, and optionally email, "
                                                            "company, code. The first row names the columns."))
