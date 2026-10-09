# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.venues.models import Room, Venue, Zone

from .models import Screen, ScreenGroup, normalize_code


class TagsField(forms.CharField):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("help_text", _("Comma separated, e.g. foyer, portrait, stage-left."))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        return ", ".join(value) if isinstance(value, list | tuple) else value

    def to_python(self, value):
        return [t.strip() for t in (value or "").split(",") if t.strip()]


def _limit_locations(form, event, prefix=""):
    venues = event.venues.all()
    form.fields[f"{prefix}venue"].queryset = venues
    form.fields[f"{prefix}zone"].queryset = Zone.objects.filter(venue__in=venues).select_related("venue")
    form.fields[f"{prefix}room"].queryset = Room.objects.filter(venue__in=venues).select_related("venue")


def _clean_location(cleaned):
    venue, zone, room = cleaned.get("venue"), cleaned.get("zone"), cleaned.get("room")
    for part in (zone, room):
        if part is not None:
            if venue is None:
                cleaned["venue"] = venue = part.venue
            elif part.venue_id != venue.pk:
                raise forms.ValidationError(_("Zone and room must belong to the selected venue."))
    return cleaned


class PairForm(forms.Form):
    code = forms.CharField(label=_("Code shown on the screen"), max_length=12,
                           widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "characters",
                                                         "spellcheck": "false", "class": "code-input"}))
    screen = forms.ModelChoiceField(label=_("Screen"), required=False, queryset=Screen.objects.none(),
                                    empty_label=_("A new screen"),
                                    help_text=_("Pick an existing screen to move it to this device (re-pair)."))
    name = forms.CharField(label=_("Name"), max_length=200, required=False,
                           help_text=_("e.g. Foyer left. Leave empty to use the code."))
    venue = forms.ModelChoiceField(label=_("Venue"), queryset=Venue.objects.none(), required=False)
    zone = forms.ModelChoiceField(label=_("Zone"), queryset=Zone.objects.none(), required=False)
    room = forms.ModelChoiceField(label=_("Room"), queryset=Room.objects.none(), required=False)
    groups = forms.ModelMultipleChoiceField(label=_("Groups"), queryset=ScreenGroup.objects.none(), required=False,
                                            widget=forms.CheckboxSelectMultiple)
    tags = TagsField(label=_("Tags"))

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["screen"].queryset = event.screens.all()
        self.fields["groups"].queryset = event.screen_groups.filter(kind=ScreenGroup.Kind.MANUAL)
        _limit_locations(self, event)

    def clean_code(self):
        code = normalize_code(self.cleaned_data["code"])
        if len(code) != 6:
            raise forms.ValidationError(_("The code has six characters, e.g. KX4-9PT."))
        return code

    def clean(self):
        return _clean_location(super().clean())


class ScreenForm(forms.ModelForm):
    tags = TagsField(label=_("Tags"))
    groups = forms.ModelMultipleChoiceField(label=_("Groups"), queryset=ScreenGroup.objects.none(), required=False,
                                            widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Screen
        fields = ["name", "description", "venue", "zone", "room", "tags"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = event.screen_groups.filter(kind=ScreenGroup.Kind.MANUAL)
        if self.instance and not self.instance._state.adding:
            self.fields["groups"].initial = list(self.instance.manual_groups.all())
        _limit_locations(self, event)

    def clean(self):
        return _clean_location(super().clean())


class ScreenGroupForm(forms.ModelForm):
    match_tags = TagsField(label=_("Tags"), help_text=_("Dynamic groups include screens with any of these tags."))

    class Meta:
        model = ScreenGroup
        fields = ["name", "description", "kind", "match_tags", "match_venues", "match_zones", "match_rooms"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2}),
                   "match_venues": forms.CheckboxSelectMultiple, "match_zones": forms.CheckboxSelectMultiple,
                   "match_rooms": forms.CheckboxSelectMultiple}
        help_texts = {"kind": _("Manual: you pick the screens. Dynamic: screens join by tag, venue, zone or room "
                                "(manually picked screens stay members too).")}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        venues = event.venues.all()
        self.fields["match_venues"].queryset = venues
        self.fields["match_zones"].queryset = Zone.objects.filter(venue__in=venues).select_related("venue")
        self.fields["match_rooms"].queryset = Room.objects.filter(venue__in=venues).select_related("venue")

    def clean_name(self):
        name = self.cleaned_data["name"]
        qs = ScreenGroup.objects.filter(event=self.event, name__iexact=name)
        if not self.instance._state.adding:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("A group with this name exists already."))
        return name
