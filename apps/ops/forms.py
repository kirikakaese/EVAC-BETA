# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from . import services
from .models import EscalationRule, Incident, LogEntry, Task


def _members(event: Any) -> Any:
    return get_user_model().objects.filter(memberships__event=event, is_active=True).order_by("display_name", "email")


def _places(form: forms.ModelForm, event: Any) -> None:
    from apps.venues.models import Room, Zone

    form.fields["zone"].queryset = Zone.objects.filter(venue__in=event.venues.all())
    form.fields["room"].queryset = Room.objects.filter(venue__in=event.venues.all())


class IncidentForm(forms.ModelForm):
    note = forms.CharField(label=_("First note"), required=False, widget=forms.Textarea(attrs={"rows": 2}),
                           help_text=_("What happened, what was done so far."))

    class Meta:
        model = Incident
        fields = ["title", "category", "severity", "zone", "room", "location", "description", "reported_by",
                  "assignee", "team"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        cats = services.categories(event)
        current = self.instance.category if self.instance and self.instance.category else ""
        if current and current not in cats:
            cats = [*cats, current]
        self.fields["category"] = forms.ChoiceField(label=_("Category"), choices=[(c, c) for c in cats],
                                                    initial=cats[0] if cats else "")
        _places(self, event)
        self.fields["assignee"].queryset = _members(event)
        if not self.instance._state.adding:
            del self.fields["note"]


class QuickIncidentForm(forms.Form):
    """The staff app's short form (works offline: replayed with its client id)."""

    title = forms.CharField(label=_("What happened?"), max_length=200)
    severity = forms.ChoiceField(label=_("Severity"), choices=Incident.Severity.choices,
                                 initial=Incident.Severity.MEDIUM)
    category = forms.CharField(label=_("Category"), max_length=40, required=False)
    location = forms.CharField(label=_("Where?"), max_length=200, required=False)


class StatusForm(forms.Form):
    status = forms.ChoiceField(label=_("Status"), choices=Incident.Status.choices)
    note = forms.CharField(label=_("Note"), required=False, max_length=500)


class NoteForm(forms.Form):
    text = forms.CharField(label=_("Note"), required=False, widget=forms.Textarea(attrs={"rows": 2}))
    attachment = forms.FileField(label=_("Photo or file"), required=False,
                                 help_text=_("Photo, PDF, text or audio, up to 10 MB."))


class LogEntryForm(forms.ModelForm):
    class Meta:
        model = LogEntry
        fields = ["sender", "recipient", "text", "important", "incident"]
        widgets = {"text": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["incident"].queryset = Incident.objects.filter(event=event, status__in=Incident.OPEN)
        self.fields["incident"].required = False


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "notes", "assignee", "team", "due_at", "incident"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2}),
                   "due_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = _members(event)
        self.fields["incident"].queryset = Incident.objects.filter(event=event)
        self.fields["due_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]


class EscalationRuleForm(forms.ModelForm):
    class Meta:
        model = EscalationRule
        fields = ["name", "enabled", "min_severity", "categories", "after_minutes", "until", "roles", "channels"]

    def __init__(self, *args: Any, event: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        from apps.core import alerts

        self.fields["categories"] = forms.MultipleChoiceField(
            label=_("Categories"), required=False, widget=forms.CheckboxSelectMultiple,
            choices=[(c, c) for c in services.categories(event)], help_text=_("None ticked: all categories."))
        self.fields["roles"].queryset = event.roles.all()
        self.fields["roles"].widget = forms.CheckboxSelectMultiple(choices=self.fields["roles"].choices)
        self.fields["roles"].help_text = _("Members with these roles get a notification (and a push on their "
                                           "phone when the staff app is installed).")
        channels = alerts.channels(event)
        self.fields["channels"] = forms.MultipleChoiceField(
            label=_("Also send to"), required=False, widget=forms.CheckboxSelectMultiple,
            choices=list(channels.items()),
            help_text=_("Channels set up under Settings → Extensions (ntfy, Matrix, Telegram, e-mail, DIAL DECT "
                        "message).") if channels else _("No channel is set up for this event (Settings → "
                                                         "Extensions: ntfy, Matrix, Telegram, e-mail, DIAL)."))
