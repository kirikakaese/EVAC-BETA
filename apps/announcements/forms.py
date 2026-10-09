# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.content.models import Layout
from apps.screens.models import Screen, ScreenGroup
from apps.venues.models import Room, Venue, Zone

from . import services
from .models import Announcement, Level, Template

LOCAL = {"type": "datetime-local"}
VAR_PREFIX = "var_"
TEXT_PREFIX = "text_"
TARGETS = ("venues", "zones", "rooms", "screen_groups", "screens")


class AnnouncementForm(forms.ModelForm):
    """Compose (or edit a draft). Texts may contain ``{{variables}}``; the fields below fill them in."""

    channels = forms.MultipleChoiceField(label=_("Channels"), widget=forms.CheckboxSelectMultiple, required=False,
                                         help_text=_("Empty: the level's default channels."))
    starts_at = forms.DateTimeField(label=_("Send at"), required=False, widget=forms.DateTimeInput(attrs=LOCAL),
                                    help_text=_("Empty: now."))

    class Meta:
        model = Announcement
        fields = ["template", "level", "title", "body", "short", "channels", "all_screens", *TARGETS, "starts_at",
                  "ends_at", "recurrence", "recurrence_until"]
        widgets = {"template": forms.HiddenInput, "body": forms.Textarea(attrs={"rows": 4}),
                   "ends_at": forms.DateTimeInput(attrs=LOCAL),
                   "recurrence_until": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, event, allow_emergency: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.instance.event = event
        levels = Level.objects.filter(event=event)
        if not allow_emergency:
            levels = levels.filter(emergency=False)
        self.fields["level"].queryset = levels
        self.fields["level"].empty_label = None
        self.fields["template"].queryset = Template.objects.filter(event=event)
        self.fields["channels"].choices = list(services.available_channels(event).items())
        venues = Venue.objects.filter(events=event)
        querysets = {"venues": venues, "zones": Zone.objects.filter(venue__in=venues),
                     "rooms": Room.objects.filter(venue__in=venues),
                     "screen_groups": ScreenGroup.objects.filter(event=event),
                     "screens": Screen.objects.filter(event=event)}
        for name, qs in querysets.items():
            self.fields[name].queryset = qs
            self.fields[name].widget = forms.CheckboxSelectMultiple(choices=self.fields[name].choices)
            self.fields[name].required = False
        self.fields["all_screens"].help_text = _("Untick to address only some venues, zones, rooms or screens.")
        self.fields["ends_at"].widget.attrs.update(LOCAL)
        template = self._template()
        names = services.variables_in(*(self.data.get(self.add_prefix(f), "") for f in ("title", "body", "short"))) \
            if self.is_bound else services.variables_in(self.initial.get("title", self.instance.title),
                                                        self.initial.get("body", self.instance.body),
                                                        self.initial.get("short", self.instance.short))
        for name in names:
            self.fields[VAR_PREFIX + name] = forms.CharField(
                label=name.replace("_", " ").capitalize(), max_length=300, required=True,
                initial=(self.instance.variables or {}).get(name, ""),
                help_text=_("Fills {{%(n)s}} in the texts.") % {"n": name})
        self.template_obj = template
        from apps.core.registry import registry

        specs = registry.ensure_loaded().notification_channels
        for key in services.available_channels(event):
            spec = specs[key]
            if spec.max_length:
                self.fields[TEXT_PREFIX + key] = forms.CharField(
                    label=_("Text for %(c)s") % {"c": spec.name}, max_length=spec.max_length, required=False,
                    initial=(self.instance.channel_texts or {}).get(key, ""),
                    widget=forms.Textarea(attrs={"rows": 2}),
                    help_text=_("Optional, at most %(n)s characters. Empty: title and text.") % {
                        "n": spec.max_length})

    def _template(self):
        pk = self.data.get(self.add_prefix("template")) if self.is_bound else (
            self.initial.get("template") or self.instance.template_id)
        if not pk:
            return None
        try:
            return Template.objects.filter(event=self.event).get(pk=pk)
        except (Template.DoesNotExist, ValueError, forms.ValidationError):
            return None

    def variable_fields(self):
        return [self[name] for name in self.fields if name.startswith(VAR_PREFIX)]

    def main_fields(self):
        return [self[n] for n in ("level", "title", "body", "short")]

    def target_fields(self):
        return [self[n] for n in ("all_screens", *TARGETS)]

    def channel_text_fields(self):
        return [self[name] for name in self.fields if name.startswith(TEXT_PREFIX)]

    def timing_fields(self):
        return [self[n] for n in ("starts_at", "ends_at", "recurrence", "recurrence_until")]

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("all_screens") and not any(cleaned.get(n) for n in TARGETS):
            raise forms.ValidationError(_("Choose where: everywhere, or some venues, zones, rooms or screens."))
        if not cleaned.get("channels") and cleaned.get("level"):
            cleaned["channels"] = [c for c in cleaned["level"].default_channels if c in dict(
                self.fields["channels"].choices)]
        cleaned["starts_at"] = cleaned.get("starts_at") or timezone.now()
        return cleaned

    def build(self) -> tuple[Announcement, dict]:
        """The announcement (unsaved, texts rendered) and its targets."""
        ann = self.save(commit=False)
        variables = {name[len(VAR_PREFIX):]: self.cleaned_data[name] for name in self.fields
                     if name.startswith(VAR_PREFIX)}
        ann.variables = variables
        ann.title = services.render_text(ann.title, variables, self.event)[:200]
        ann.body = services.render_text(ann.body, variables, self.event)
        ann.short = services.render_text(ann.short, variables, self.event)[:160]
        ann.channels = list(self.cleaned_data["channels"])
        ann.channel_texts = {name[len(TEXT_PREFIX):]: self.cleaned_data[name].strip() for name in self.fields
                             if name.startswith(TEXT_PREFIX) and self.cleaned_data.get(name, "").strip()}
        ann.starts_at = self.cleaned_data["starts_at"]
        m2m = {n: list(self.cleaned_data.get(n) or []) for n in TARGETS}
        if ann.all_screens:
            m2m = {n: [] for n in TARGETS}
        return ann, m2m


class LevelForm(forms.ModelForm):
    default_channels = forms.MultipleChoiceField(label=_("Default channels"), required=False,
                                                 widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Level
        fields = ["name", "rank", "colour", "display", "sound", "min_display_seconds", "repeat_every_minutes",
                  "default_channels", "requires_approval"]
        widgets = {"colour": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_channels"].choices = list(services.available_channels(event).items())

    def clean_colour(self):
        value = self.cleaned_data["colour"]
        import re

        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""):
            raise forms.ValidationError(_("A colour like #2563eb."))
        return value.lower()


class TemplateForm(forms.ModelForm):
    class Meta:
        model = Template
        fields = ["name", "level", "title", "body", "short", "layout"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.event = event
        self.fields["level"].queryset = Level.objects.filter(event=event)
        self.fields["layout"].queryset = Layout.objects.filter(event=event)
        self.fields["layout"].required = False
        self.fields["body"].help_text = _("Use {{name}} for parts filled in when sending, e.g. {{desk}}.")


class DecisionForm(forms.Form):
    note = forms.CharField(label=_("Note"), max_length=300, required=False)
