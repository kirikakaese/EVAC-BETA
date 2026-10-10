# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Session, Speaker, Stage, Track


class SessionForm(forms.ModelForm):
    speakers_text = forms.CharField(label=_("Speakers"), required=False, max_length=1000,
                                    help_text=_("Names, separated by commas."))

    class Meta:
        model = Session
        fields = ["title", "subtitle", "starts_at", "ends_at", "stage", "track", "kind", "language", "abstract",
                  "url", "note", "public"]
        widgets = {"starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "abstract": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.event = event
        self.fields["stage"].queryset = Stage.objects.filter(event=event)
        self.fields["track"].queryset = Track.objects.filter(event=event)
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
        if self.instance.pk and not self.instance._state.adding:
            self.fields["speakers_text"].initial = ", ".join(p.name for p in self.instance.speakers.all())

    def speakers(self) -> list[Speaker]:
        out = []
        for name in (self.cleaned_data.get("speakers_text") or "").split(","):
            name = name.strip()[:200]
            if name:
                sp = Speaker.objects.filter(event=self.event, name=name).first() or Speaker.objects.create(
                    event=self.event, name=name)
                out.append(sp)
        return out


class StageForm(forms.ModelForm):
    class Meta:
        model = Stage
        fields = ["name", "room", "order"]

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.venues.models import Room

        self.fields["room"].queryset = Room.objects.filter(venue__in=event.venues.all())
        self.fields["room"].help_text = _("Screens in this room show this stage's sessions in “now and next”.")


class TrackForm(forms.ModelForm):
    class Meta:
        model = Track
        fields = ["name", "colour"]
        widgets = {"colour": forms.TextInput(attrs={"type": "color"})}
