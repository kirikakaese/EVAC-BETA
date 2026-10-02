# SPDX-License-Identifier: AGPL-3.0-or-later
from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:", "ATOMIC_REQUESTS": True}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EVAC_SECRETS_KEYS = ["XomAWuiwOEn3rbi3Tu8qc4mYTpacjllvDaRBicGHLuI="]
EVAC_OIDC_ENABLED = False
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
