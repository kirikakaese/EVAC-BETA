# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import zoneinfo

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.registry import registry
from apps.events.models import Event, Role
from apps.venues.models import Venue

TZ_CHOICES = [(tz, tz) for tz in sorted(zoneinfo.available_timezones()) if "/" in tz or tz == "UTC"]
DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class SetupAdminForm(forms.Form):
    setup_token = forms.CharField(label=_("Setup token"), required=False,
                                  help_text=_("Printed in the server log when EVAC_SETUP_TOKEN is set."))
    email = forms.EmailField(label=_("Your e-mail address"))
    display_name = forms.CharField(label=_("Your name"), max_length=120, required=False)
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label=_("Repeat the password"),
                                widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, token_required=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.token_required = token_required
        if not token_required:
            del self.fields["setup_token"]

    def clean(self):
        data = super().clean()
        if data.get("password1") != data.get("password2"):
            raise ValidationError(_("The passwords do not match."))
        if data.get("password1"):
            validate_password(data["password1"], User(email=data.get("email", "")))
        return data


class VenueForm(forms.ModelForm):
    timezone = forms.ChoiceField(choices=TZ_CHOICES, initial="UTC", label=_("Time zone"))

    class Meta:
        model = Venue
        fields = ["name", "slug", "timezone", "address", "description", "is_permanent", "latitude", "longitude"]
        widgets = {"address": forms.Textarea(attrs={"rows": 2}), "description": forms.Textarea(attrs={"rows": 3})}
        help_texts = {"slug": _("Short name used in URLs and exports.")}


class EventForm(forms.ModelForm):
    timezone = forms.ChoiceField(choices=TZ_CHOICES, initial="UTC", label=_("Time zone"))

    class Meta:
        model = Event
        fields = ["name", "slug", "description", "timezone", "start_date", "end_date", "venues", "primary_color",
                  "accent_color", "logo"]
        widgets = {"start_date": DATE, "end_date": DATE, "description": forms.Textarea(attrs={"rows": 3}),
                   "primary_color": forms.TextInput(attrs={"type": "color"}),
                   "accent_color": forms.TextInput(attrs={"type": "color"}),
                   "venues": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance._state.adding:
            self.fields["slug"].disabled = True
            self.fields["slug"].help_text = _("The short name cannot be changed after creation.")


class SetupEventForm(EventForm):
    """The wizard's event step. Modules with a statement to accept (the evacuation module) can be switched on here:
    the statement is shown and must be accepted (brief §2)."""

    class Meta(EventForm.Meta):
        fields = ["name", "slug", "timezone", "start_date", "end_date"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.registry import registry

        self.ack_modules = [m for m in registry.ensure_loaded().modules.values() if m.acknowledgement]
        for m in self.ack_modules:
            self.fields[f"use_{m.key}"] = forms.BooleanField(
                required=False, label=_("Use the %(m)s module in this event, and accept its statement") % {
                    "m": m.name}, help_text=m.acknowledgement)

    def modules_to_enable(self) -> list[str]:
        return [m.key for m in self.ack_modules if self.cleaned_data.get(f"use_{m.key}")]


class TransitionForm(forms.Form):
    state = forms.ChoiceField(choices=Event.State.choices)
    reason = forms.CharField(required=False, max_length=300, label=_("Note for the audit log"))


class ScheduleForm(forms.Form):
    target_state = forms.ChoiceField(choices=Event.State.choices, label=_("Move to"))
    at = forms.DateTimeField(label=_("At"), widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))


class CloneForm(forms.Form):
    name = forms.CharField(max_length=200, label=_("Name of the new event"))
    slug = forms.SlugField(max_length=50, required=False, label=_("Short name"))
    with_content = forms.BooleanField(required=False, label=_("Copy content and members too"))


class ImportForm(forms.Form):
    file = forms.FileField(label=_("Export file (JSON)"))
    slug = forms.SlugField(max_length=50, required=False, label=_("Short name for the imported event"))
    name = forms.CharField(max_length=200, required=False, label=_("Name (default: from the file)"))


def permission_choices():
    reg = registry.ensure_loaded()
    groups: dict[str, list[tuple[str, str]]] = {}
    for key, spec in sorted(reg.permissions.items()):
        label = spec.label + (" *" if spec.sensitive else "")
        groups.setdefault(spec.module, []).append((key, f"{key} - {label}"))
    return [(mod, items) for mod, items in sorted(groups.items())]


class RoleForm(forms.ModelForm):
    patterns = forms.CharField(
        label=_("Additional patterns"), required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text=_("Glob patterns, one per line, e.g. 'screens.*', '*.view' or '!events.delete' to exclude. "
                    "Patterns also match permissions of modules installed later."))
    perms = forms.MultipleChoiceField(label=_("Permissions"), required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = Role
        fields = ["name", "key", "description", "require_2fa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["perms"].choices = permission_choices()
        known = set(registry.permission_keys())
        current = list(self.instance.permissions or []) if self.instance.pk else []
        self.fields["perms"].initial = [p for p in current if p in known]
        self.fields["patterns"].initial = "\n".join(p for p in current if p not in known)
        if self.instance.pk:
            self.fields["key"].disabled = True

    def permission_list(self) -> list[str]:
        pats = [p.strip() for p in self.cleaned_data.get("patterns", "").splitlines() if p.strip()]
        return list(self.cleaned_data.get("perms", [])) + pats


class InviteForm(forms.Form):
    email = forms.EmailField(label=_("E-mail address"))
    role = forms.ModelChoiceField(queryset=Role.objects.none(), label=_("Role"))
    scope = forms.ChoiceField(label=_("Limited to"), required=False)

    def __init__(self, *args, event, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = event.roles.all()
        choices = [("", _("Whole event"))]
        for kind in registry.ensure_loaded().scope_kinds.values():
            items = kind.choices(event)
            if items:
                choices.append((kind.label, [(f"{kind.key}:{i}", label) for i, label in items]))
        self.fields["scope"].choices = choices

    def scope_parts(self) -> tuple[str, str]:
        raw = self.cleaned_data.get("scope") or ""
        kind, _sep, sid = raw.partition(":")
        return kind, sid


class ModuleToggleForm(forms.Form):
    key = forms.CharField()
    value = forms.ChoiceField(choices=[("on", "on"), ("off", "off"), ("inherit", "inherit")])
