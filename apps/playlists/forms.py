# SPDX-License-Identifier: AGPL-3.0-or-later
import datetime as dt

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.content.models import Layout
from apps.screens.forms import TagsField
from apps.screens.models import Screen, ScreenGroup

from .models import Override, Playlist, PlaylistItem, ScheduleRule

LOCAL = {"type": "datetime-local"}
WEEKDAYS = [(0, _("Mon")), (1, _("Tue")), (2, _("Wed")), (3, _("Thu")), (4, _("Fri")), (5, _("Sat")), (6, _("Sun"))]


def _layouts(event):
    return Layout.objects.filter(event=event).select_related("published")


class PlaylistForm(forms.ModelForm):
    class Meta:
        model = Playlist
        fields = ["name", "description", "mode", "default_duration", "is_default"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

    def clean_name(self):
        name = self.cleaned_data["name"]
        qs = Playlist.objects.filter(event=self.event, name__iexact=name)
        if not self.instance._state.adding:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("A playlist with this name exists."))
        return name


class ItemForm(forms.ModelForm):
    tags = TagsField(label=_("Only on screens tagged"),
                     help_text=_("Comma separated. Empty: every screen."))

    class Meta:
        model = PlaylistItem
        fields = ["layout", "child", "duration", "weight", "tags", "condition", "valid_from", "valid_until",
                  "enabled"]
        widgets = {"valid_from": forms.DateTimeInput(attrs=LOCAL), "valid_until": forms.DateTimeInput(attrs=LOCAL)}

    def __init__(self, *args, playlist, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.playlist = playlist
        self.fields["layout"].queryset = _layouts(playlist.event)
        self.fields["layout"].empty_label = _("—")
        self.fields["child"].queryset = Playlist.objects.filter(event=playlist.event).exclude(pk=playlist.pk)
        self.fields["child"].empty_label = _("—")
        self.fields["child"].help_text = _("Or play another playlist at this position.")

    def clean(self):
        cleaned = super().clean()
        if bool(cleaned.get("layout")) == bool(cleaned.get("child")):
            raise forms.ValidationError(_("Choose either a layout or a nested playlist."))
        return cleaned


class TargetMixin(forms.Form):
    def setup_targets(self, event):
        self.fields["groups"].queryset = ScreenGroup.objects.filter(event=event)
        self.fields["screens"].queryset = Screen.objects.filter(event=event)
        for name in ("groups", "screens"):
            self.fields[name].widget = forms.CheckboxSelectMultiple(choices=self.fields[name].choices)
            self.fields[name].required = False

    def check_targets(self, cleaned):
        if not (cleaned.get("all_screens") or cleaned.get("groups") or cleaned.get("screens")):
            raise forms.ValidationError(_("Choose the screens: all, groups or single screens."))


class ScheduleForm(TargetMixin, forms.ModelForm):
    weekdays = forms.TypedMultipleChoiceField(label=_("Weekdays"), choices=WEEKDAYS, coerce=int, required=False,
                                              widget=forms.CheckboxSelectMultiple,
                                              help_text=_("None ticked: every day."))

    class Meta:
        model = ScheduleRule
        fields = ["name", "enabled", "playlist", "layout", "all_screens", "groups", "screens", "weekdays",
                  "start_time", "end_time", "start_date", "end_date", "priority"]
        widgets = {"start_time": forms.TimeInput(attrs={"type": "time"}),
                   "end_time": forms.TimeInput(attrs={"type": "time"}),
                   "start_date": forms.DateInput(attrs={"type": "date"}),
                   "end_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        self.fields["playlist"].queryset = Playlist.objects.filter(event=event)
        self.fields["layout"].queryset = _layouts(event)
        self.fields["layout"].help_text = _("Or show a single layout.")
        self.fields["priority"].widget.attrs.update(min=0, max=99)
        self.setup_targets(event)

    def clean(self):
        cleaned = super().clean()
        if bool(cleaned.get("layout")) == bool(cleaned.get("playlist")):
            raise forms.ValidationError(_("Choose either a playlist or a layout."))
        self.check_targets(cleaned)
        return cleaned

    def clean_priority(self):
        value = self.cleaned_data["priority"]
        if value > 99:
            raise forms.ValidationError(_("At most 99."))
        return value


DURATIONS = [("5", _("5 minutes")), ("15", _("15 minutes")), ("30", _("30 minutes")), ("60", _("1 hour")),
             ("120", _("2 hours")), ("240", _("4 hours")), ("", _("Until cancelled")), ("custom", _("Until …"))]


class OverrideForm(TargetMixin, forms.ModelForm):
    duration = forms.ChoiceField(label=_("Duration"), choices=DURATIONS, initial="15", required=False)
    until = forms.DateTimeField(label=_("Until"), required=False, widget=forms.DateTimeInput(attrs=LOCAL),
                                help_text=_("Only for “Until …”."))
    start_later = forms.DateTimeField(label=_("Start at"), required=False, widget=forms.DateTimeInput(attrs=LOCAL),
                                      help_text=_("Empty: now."))

    class Meta:
        model = Override
        fields = ["title", "level", "message", "layout", "playlist", "all_screens", "groups", "screens"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, event, allow_emergency: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        self.fields["layout"].queryset = _layouts(event)
        self.fields["playlist"].queryset = Playlist.objects.filter(event=event)
        self.fields["layout"].help_text = _("Or a layout, …")
        self.fields["playlist"].help_text = _("… or a playlist instead of the message.")
        if not allow_emergency:
            self.fields["level"].choices = [c for c in Override.Level.choices if c[0] != Override.Level.EMERGENCY]
        self.setup_targets(event)

    def clean(self):
        cleaned = super().clean()
        picked = [k for k in ("layout", "playlist") if cleaned.get(k)]
        if len(picked) > 1:
            raise forms.ValidationError(_("Choose a layout or a playlist, not both."))
        if not picked and not (cleaned.get("message") or "").strip():
            raise forms.ValidationError(_("Write a message or choose a layout or playlist."))
        self.check_targets(cleaned)
        start = cleaned.get("start_later") or timezone.now()
        duration = cleaned.get("duration")
        if duration == "custom":
            if not cleaned.get("until"):
                self.add_error("until", _("Choose when it ends."))
            cleaned["expires_at"] = cleaned.get("until")
        else:
            cleaned["expires_at"] = start + dt.timedelta(minutes=int(duration)) if duration else None
        if cleaned["expires_at"] and cleaned["expires_at"] <= start:
            self.add_error("until", _("Must be after the start."))
        cleaned["starts_at"] = start
        return cleaned


class PreviewForm(forms.Form):
    screen = forms.ModelChoiceField(label=_("Screen"), queryset=Screen.objects.none())
    at = forms.DateTimeField(label=_("At"), required=False, widget=forms.DateTimeInput(attrs=LOCAL),
                             help_text=_("Empty: now."))

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["screen"].queryset = Screen.objects.filter(event=event)


class CalendarForm(forms.Form):
    group = forms.ModelChoiceField(label=_("Screen group"), queryset=ScreenGroup.objects.none(), required=False,
                                   empty_label=_("All screens"))
    week = forms.DateField(label=_("Week of"), required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["group"].queryset = ScreenGroup.objects.filter(event=event)
