# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Area


class AreaForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = ["name", "room", "zone", "capacity", "busy_percent", "full_percent", "release_percent",
                  "show_on_screens", "screen_groups", "alternative", "full_text", "notify_roles", "channels",
                  "sensor_key", "order"]

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.core import alerts
        from apps.screens.models import ScreenGroup
        from apps.venues.models import Room, Zone

        self.fields["room"].queryset = Room.objects.filter(venue__in=event.venues.all())
        self.fields["zone"].queryset = Zone.objects.filter(venue__in=event.venues.all())
        self.fields["screen_groups"].queryset = ScreenGroup.objects.filter(event=event)
        self.fields["screen_groups"].widget = forms.CheckboxSelectMultiple(
            choices=self.fields["screen_groups"].choices)
        alt = Area.objects.filter(event=event)
        if not self.instance._state.adding:
            alt = alt.exclude(pk=self.instance.pk)
        self.fields["alternative"].queryset = alt
        self.fields["notify_roles"].queryset = event.roles.all()
        self.fields["notify_roles"].widget = forms.CheckboxSelectMultiple(choices=self.fields["notify_roles"].choices)
        channels = alerts.channels(event)
        self.fields["channels"] = forms.MultipleChoiceField(
            label=_("Also alert channels"), required=False, widget=forms.CheckboxSelectMultiple,
            choices=list(channels.items()),
            help_text=_("Channels set up under Settings → Extensions.") if channels else
            _("No channel is set up for this event (Settings → Extensions)."))
        self.fields["capacity"].required = False
        for f in ("busy_percent", "full_percent", "release_percent"):
            self.fields[f].widget.attrs.update({"min": 1, "max": 200})

    def clean(self) -> dict[str, Any]:
        data = super().clean()
        room, zone = data.get("room"), data.get("zone")
        if not data.get("capacity"):
            # the room's (or zone's) capacity unless one is given
            data["capacity"] = (room.capacity if room and room.capacity else
                                (zone.capacity if zone and zone.capacity else 0))
            self.instance.capacity = data["capacity"]
        if zone and room:
            raise forms.ValidationError(_("Choose a room or a zone, not both."))
        return data


class CorrectionForm(forms.Form):
    value = forms.IntegerField(label=_("People in the area now"), min_value=0, max_value=1_000_000)
