# SPDX-License-Identifier: AGPL-3.0-or-later
"""OpenAPI (drf-spectacular) integration: document the service token security scheme."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ServiceTokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.api.authentication.ServiceTokenAuthentication"
    name = "ServiceToken"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "evac_<token>",
                "description": "Service token from Account -> API tokens (or `manage.py evac_token`)."}
