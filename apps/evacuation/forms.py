# SPDX-License-Identifier: AGPL-3.0-or-later
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from .machine import SEVERITY, State

EVENT = "event"


class ChangeForm(forms.Form):
    scope = forms.ChoiceField(label=_("Where"))
    state = forms.ChoiceField(label=_("New state"))
    drill = forms.BooleanField(label=_("Drill"), required=False,
                               help_text=_("Screens show the drill marker; notifications are prefixed."))
    reason = forms.CharField(label=_("Note"), required=False, max_length=300,
                             help_text=_("Optional. Stored in the history and the audit log."))
    clear_zones = forms.MultipleChoiceField(
        label=_("All clear for the whole event also clears these zones"), required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Untick a zone to keep its own alarm."))

    def __init__(self, *args: Any, zones: Any, labels: dict[str, str], enabled: frozenset[State],
                 alarm_zones: list[Any], can_drill: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["scope"].choices = [(EVENT, _("Whole event"))] + [
            (str(z.pk), f"{z.venue.name} · {z.name}") for z in zones]
        states = sorted((s for s in enabled if s is not State.NORMAL), key=lambda s: -SEVERITY[s])
        self.fields["state"].choices = [(s.value, labels[s.value]) for s in states]
        self.fields["clear_zones"].choices = [(str(z.pk), f"{z.venue.name} · {z.name}") for z in alarm_zones]
        self.initial.setdefault("clear_zones", [str(z.pk) for z in alarm_zones])
        if not alarm_zones:
            del self.fields["clear_zones"]
        if not can_drill:
            del self.fields["drill"]


class PolicyForm(forms.Form):
    source = forms.ChoiceField(label=_("Source"))
    state = forms.ChoiceField(label=_("Stage"), required=False)
    zone = forms.ChoiceField(label=_("Zone"), required=False)
    action = forms.ChoiceField(label=_("Action"), choices=[
        ("execute", _("Execute at once")), ("arm", _("Arm: the control room confirms")),
        ("notify", _("Only notify the control room"))])
    escalate_seconds = forms.IntegerField(
        label=_("Auto-escalate after (seconds)"), required=False, min_value=10, max_value=3600, initial=120,
        help_text=_("Arm only: execute when nobody confirms or rejects in time. Empty: wait for a person."))

    def __init__(self, *args: Any, sources: list[tuple[str, str]], zones: Any, labels: dict[str, str],
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["source"].choices = sources
        self.fields["state"].choices = [("", _("Every stage"))] + [
            (s.value, labels[s.value]) for s in State if s not in (State.NORMAL, State.ALL_CLEAR)]
        self.fields["zone"].choices = [("", _("Every zone and the whole event"))] + [
            (str(z.pk), f"{z.venue.name} · {z.name}") for z in zones]


class DrillForm(forms.Form):
    at = forms.DateTimeField(label=_("Starts at"), widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
                             input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"])
    state = forms.ChoiceField(label=_("Stage"))
    zone = forms.ChoiceField(label=_("Where"), required=False)
    note = forms.CharField(label=_("Note"), required=False, max_length=300)

    def __init__(self, *args: Any, zones: Any, labels: dict[str, str], enabled: frozenset[State],
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["state"].choices = [(s.value, labels[s.value]) for s in sorted(
            (s for s in enabled if s not in (State.NORMAL, State.ALL_CLEAR)), key=lambda s: -SEVERITY[s])]
        self.fields["zone"].choices = [("", _("Whole event"))] + [
            (str(z.pk), f"{z.venue.name} · {z.name}") for z in zones]
