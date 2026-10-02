# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import ServiceToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "display_name", "is_superuser", "is_active", "email_verified", "date_joined"]
    search_fields = ["email", "display_name"]
    fieldsets = (
        (None, {"fields": ("email", "password", "display_name")}),
        ("Status", {"fields": ("is_active", "is_staff", "is_superuser", "email_verified", "oidc_subject")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
    filter_horizontal = ()
    list_filter = ["is_superuser", "is_active"]


@admin.register(ServiceToken)
class ServiceTokenAdmin(admin.ModelAdmin):
    list_display = ["name", "owner", "event", "token_prefix", "is_active", "last_used_at", "expires_at"]
    readonly_fields = ["token_prefix", "created_with_2fa", "last_used_at"]
    exclude = ["token_hash"]
