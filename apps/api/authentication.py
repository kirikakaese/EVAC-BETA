# SPDX-License-Identifier: AGPL-3.0-or-later
"""Service token authentication (``Authorization: Bearer evac_...``)."""
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import authentication, exceptions

from apps.accounts.models import ServiceToken


class ServiceTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode(errors="ignore")
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() not in ("bearer", "token") or not parts[1].startswith("evac_"):
            return None
        tok = (ServiceToken.objects.select_related("owner", "event")
               .filter(token_hash=ServiceToken.hash_token(parts[1]), is_active=True).first())
        if tok is None:
            raise exceptions.AuthenticationFailed(_("Invalid service token."))
        if tok.is_expired:
            raise exceptions.AuthenticationFailed(_("Service token expired."))
        if not tok.owner.is_active:
            raise exceptions.AuthenticationFailed(_("Owner account disabled."))
        ServiceToken.objects.filter(pk=tok.pk).update(last_used_at=timezone.now())
        request._request.service_token = tok
        return (tok.owner, tok)

    def authenticate_header(self, request):
        return self.keyword
