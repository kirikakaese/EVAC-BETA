# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import ServiceToken, User
from apps.core.models import AuditLog
from apps.events.models import Event, Membership, Role, RoleAssignment
from apps.venues.models import Building, Floor, Room, Venue, Zone


class UserSerializer(serializers.ModelSerializer):
    has_two_factor = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "is_superuser", "email_verified", "has_two_factor"]
        read_only_fields = fields


class EventSerializer(serializers.ModelSerializer):
    venues = serializers.SlugRelatedField(slug_field="slug", many=True, queryset=Venue.objects.all(), required=False)

    class Meta:
        model = Event
        fields = ["id", "slug", "name", "description", "state", "timezone", "start_date", "end_date", "venues",
                  "primary_color", "accent_color", "default_theme", "created_at", "updated_at"]
        read_only_fields = ["id", "state", "created_at", "updated_at"]

    def validate(self, attrs):
        inst = Event(**{**({f.name: getattr(self.instance, f.name) for f in Event._meta.concrete_fields}
                           if self.instance else {}), **{k: v for k, v in attrs.items() if k != "venues"}})
        inst.clean()
        return attrs


class TransitionSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=Event.State.choices)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class CloneSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    slug = serializers.SlugField(required=False, allow_blank=True)
    with_content = serializers.BooleanField(default=False)


class RoleSerializer(serializers.ModelSerializer):
    effective_permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "key", "name", "description", "permissions", "require_2fa", "builtin", "order",
                  "effective_permissions"]
        read_only_fields = ["id", "builtin", "effective_permissions"]

    def get_effective_permissions(self, obj) -> list[str]:
        return sorted(obj.expanded())

    def validate_permissions(self, value):
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            raise serializers.ValidationError("A list of permission patterns is required.")
        return value


class AssignmentSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field="key", read_only=True)

    class Meta:
        model = RoleAssignment
        fields = ["id", "role", "scope_kind", "scope_id", "scope_label"]


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    assignments = AssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "assignments", "created_at"]


class AssignRoleSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.SlugField()
    scope_kind = serializers.CharField(required=False, allow_blank=True, default="")
    scope_id = serializers.CharField(required=False, allow_blank=True, default="")
    invite = serializers.BooleanField(default=True, help_text="Send an invitation if no account exists.")


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "created_at", "actor_repr", "event_repr", "action", "target_type", "target_id",
                  "target_repr", "scope", "message", "changes", "ip_address", "drill", "prev_hash", "hash"]


class ModuleStateSerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    required = serializers.BooleanField(read_only=True)
    instance = serializers.BooleanField(read_only=True)
    event = serializers.BooleanField(allow_null=True)
    active = serializers.BooleanField(read_only=True)


class TokenSerializer(serializers.ModelSerializer):
    event = serializers.SlugRelatedField(slug_field="slug", queryset=Event.objects.all(), required=False,
                                         allow_null=True)
    token = serializers.CharField(read_only=True, help_text="Only returned once, on creation.")

    class Meta:
        model = ServiceToken
        fields = ["id", "name", "event", "scopes", "token_prefix", "is_active", "created_with_2fa", "created_at",
                  "last_used_at", "expires_at", "token"]
        read_only_fields = ["id", "token_prefix", "created_with_2fa", "created_at", "last_used_at", "token"]


class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ["id", "slug", "name", "description", "address", "timezone", "latitude", "longitude",
                  "is_permanent", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class BuildingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Building
        fields = ["id", "venue", "name", "outdoor", "order"]


class FloorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Floor
        fields = ["id", "building", "name", "level"]


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ["id", "venue", "name", "outdoor", "capacity", "color"]


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "venue", "floor", "zones", "name", "capacity", "step_free", "has_lift", "wheelchair_spaces"]

    def validate(self, attrs):
        venue = attrs.get("venue") or getattr(self.instance, "venue", None)
        floor = attrs.get("floor")
        if floor is not None and venue is not None and floor.building.venue_id != venue.pk:
            raise serializers.ValidationError({"floor": "Floor belongs to another venue."})
        for z in attrs.get("zones", []):
            if venue is not None and z.venue_id != venue.pk:
                raise serializers.ValidationError({"zones": "Zone belongs to another venue."})
        return attrs
