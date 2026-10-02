# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms

from .models import Building, Floor, Room, Zone


class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = ["name", "outdoor", "order"]


class FloorForm(forms.ModelForm):
    class Meta:
        model = Floor
        fields = ["building", "name", "level"]

    def __init__(self, *args, venue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["building"].queryset = venue.buildings.all()


class ZoneForm(forms.ModelForm):
    class Meta:
        model = Zone
        fields = ["name", "outdoor", "capacity", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["name", "floor", "zones", "capacity", "step_free", "has_lift", "wheelchair_spaces"]
        widgets = {"zones": forms.CheckboxSelectMultiple}

    def __init__(self, *args, venue, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["floor"].queryset = Floor.objects.filter(building__venue=venue).select_related("building")
        self.fields["zones"].queryset = venue.zones.all()
