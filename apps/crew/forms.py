# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .models import Member, Shift, Skill, Team


def _checkboxes(field: forms.Field) -> None:
    field.widget = forms.CheckboxSelectMultiple(choices=field.choices)


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ["name", "description", "colour", "meeting_point", "leads"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2}), "colour": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["leads"].queryset = get_user_model().objects.filter(memberships__event=event, is_active=True)
        _checkboxes(self.fields["leads"])


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ["name", "contact", "user", "teams", "skills", "arrived", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = get_user_model().objects.filter(memberships__event=event, is_active=True)
        self.fields["user"].help_text = _("With an account they sign up and check in themselves in the staff app.")
        self.fields["teams"].queryset = Team.objects.filter(event=event)
        self.fields["skills"].queryset = Skill.objects.filter(event=event)
        _checkboxes(self.fields["teams"])
        _checkboxes(self.fields["skills"])


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = ["team", "title", "shift_type", "room", "location", "starts_at", "ends_at", "needed", "skills",
                  "open_signup", "notes"]
        widgets = {"starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, event: Any, teams: Any = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.venues.models import Room

        from .models import ShiftType

        self.fields["team"].queryset = teams if teams is not None else Team.objects.filter(event=event)
        self.fields["shift_type"].queryset = ShiftType.objects.filter(event=event)
        self.fields["room"].queryset = Room.objects.filter(venue__in=event.venues.all())
        self.fields["skills"].queryset = Skill.objects.filter(event=event)
        _checkboxes(self.fields["skills"])
        for name in ("starts_at", "ends_at"):
            self.fields[name].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]


class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = ["name"]


class AddPersonForm(forms.Form):
    member = forms.ModelChoiceField(label=_("Add a crew member"), queryset=Member.objects.none())

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = Member.objects.filter(event=event)
