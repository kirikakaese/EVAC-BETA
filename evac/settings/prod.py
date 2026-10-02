# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env

DEBUG = False
if SECRET_KEY in ("insecure-dev-key-change-me", "change-me", "") and not env.bool("EVAC_ALLOW_INSECURE", default=False):
    raise ImproperlyConfigured("Set SECRET_KEY (and EVAC_SECRETS_KEYS) for production.")
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
