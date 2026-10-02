# SPDX-License-Identifier: AGPL-3.0-or-later
"""Base settings shared by all environments.

Configuration is read from environment variables (12-factor) so the same image runs in Docker Compose,
on an Ansible-managed host, or on a venue node with no internet connection.
"""
from importlib.metadata import entry_points
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["*"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DATABASE_URL=(str, f"sqlite:///{BASE_DIR / 'evac.sqlite3'}"),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    TIME_ZONE=(str, "UTC"),
    EMAIL_URL=(str, "consolemail://"),
    DEFAULT_FROM_EMAIL=(str, "evac@example.org"),
    EVAC_MODE=(str, "central"),
    EVAC_PUBLIC_URL=(str, "http://localhost:8000"),
    EVAC_REALTIME_URL=(str, ""),
    EVAC_SECRETS_KEYS=(list, []),
    EVAC_SEED_DEMO=(bool, False),
    EVAC_EARLY_ACCESS_PASSWORD=(str, ""),
    EVAC_EARLY_ACCESS_DAYS=(int, 30),
    EVAC_EARLY_ACCESS_MESSAGE=(str, ""),
    EVAC_DISABLED_PLUGINS=(list, []),
    EVAC_LOGIN_MAX_FAILURES=(int, 5),
    EVAC_LOGIN_LOCKOUT_MINUTES=(int, 15),
    EVAC_INVITATION_TTL_HOURS=(int, 168),
    EVAC_WEBHOOK_TIMEOUT=(int, 5),
    EVAC_OUTBOX_MAX_ATTEMPTS=(int, 8),
    # OpenID Connect login (same approach as PET)
    EVAC_OIDC_ENABLED=(bool, False),
    EVAC_OIDC_ISSUER=(str, ""),
    EVAC_OIDC_CLIENT_ID=(str, ""),
    EVAC_OIDC_CLIENT_SECRET=(str, ""),
    EVAC_OIDC_SCOPES=(str, "openid email profile"),
    EVAC_OIDC_BUTTON_LABEL=(str, "Log in with SSO"),
    EVAC_OIDC_AUTO_CREATE=(bool, True),
    EVAC_OIDC_TRUST_EMAIL_VERIFIED=(bool, True),
    EVAC_OIDC_ALLOW_PASSWORD_LOGIN=(bool, True),
    EVAC_OIDC_TRUST_MFA=(bool, False),
    EVAC_WEBAUTHN_RP_ID=(str, ""),
    EVAC_WEBAUTHN_RP_NAME=(str, "EVAC"),
    SENTRY_DSN=(str, ""),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

# "central" = the permanent multi-event service; "node" = a venue node (see docs/adr/0002-central-node-sync.md).
EVAC_MODE = env("EVAC_MODE")
EVAC_PUBLIC_URL = env("EVAC_PUBLIC_URL").rstrip("/")
# Where browsers open WebSockets. Empty = same origin (a reverse proxy routes /ws/ to the channels service).
# docker-compose sets it to the channels port for a proxy-less laptop setup. SSE/long-poll stay same-origin.
EVAC_REALTIME_URL = env("EVAC_REALTIME_URL").rstrip("/")
EVAC_SEED_DEMO = env("EVAC_SEED_DEMO")

# --------------------------------------------------------------------------- apps / plugins
# Every module and extension is a plugin (a Django app with an ``evac_plugin`` manifest, see
# apps/core/plugins.py). Built-in plugins are listed here; third-party plugins are discovered through the
# ``evac.plugins`` entry point group. EVAC_DISABLED_PLUGINS removes plugins at install level (an app that
# is not installed has no tables, URLs or tasks - different from switching a module off in the UI).
EVAC_CORE_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.events",
    "apps.venues",
    "apps.extensions",
    "apps.api",
    "apps.portal",
]
EVAC_BUILTIN_PLUGINS = [
    "extensions.webhooks",
]
_disabled = set(env("EVAC_DISABLED_PLUGINS"))


def _entry_point_plugins() -> list[str]:
    try:
        return [ep.value for ep in entry_points(group="evac.plugins")]
    except Exception:  # pragma: no cover - broken metadata must not prevent startup
        return []


EVAC_PLUGIN_APPS = [p for p in EVAC_BUILTIN_PLUGINS + _entry_point_plugins() if p not in _disabled]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "drf_spectacular",
    "django_filters",
    "channels",
    *EVAC_CORE_APPS,
    *EVAC_PLUGIN_APPS,
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RateLimitMiddleware",
    "apps.core.early_access.EarlyAccessMiddleware",
    "apps.core.middleware.FirstRunMiddleware",
    "apps.core.middleware.CurrentEventMiddleware",
]

ROOT_URLCONF = "evac.urls"
WSGI_APPLICATION = "evac.wsgi.application"
ASGI_APPLICATION = "evac.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.evac",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"].setdefault("CONN_MAX_AGE", 60)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "portal:home"
LOGOUT_REDIRECT_URL = "accounts:login"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

# --------------------------------------------------------------------------- language
# This build ships English only. Strings are still wrapped in gettext so a locale can be added later
# without refactoring, but no catalog exists and only "en" is configured (see CLAUDE.md, "Language").
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English")]
LOCALE_PATHS: list[Path] = []
USE_I18N = True
TIME_ZONE = env("TIME_ZONE")
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

EMAIL_CONFIG = env.email_url("EMAIL_URL")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# Strict CSP: no inline scripts or handlers anywhere. Inline <style> is allowed only with the per-request
# nonce (event branding colours). Sandboxed custom code (Phase 1) gets its own, separate policy.
EVAC_CSP = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'", "'nonce'"],
    "img-src": ["'self'", "data:", "blob:"],
    "font-src": ["'self'", "data:"],
    "connect-src": ["'self'", "ws:", "wss:"],
    "media-src": ["'self'", "blob:"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
}

# --------------------------------------------------------------------------- celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "core-drain-outbox": {"task": "apps.core.tasks.drain_outbox", "schedule": 5.0},
    "core-purge-outbox": {"task": "apps.core.tasks.purge_delivered_outbox", "schedule": 86400.0},
    "events-apply-scheduled-transitions": {"task": "apps.events.tasks.apply_scheduled_transitions",
                                           "schedule": 60.0},
    "accounts-purge-expired-invitations": {"task": "apps.accounts.tasks.purge_expired_invitations",
                                           "schedule": 86400.0},
}

# --------------------------------------------------------------------------- REST framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.ServiceTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated", "apps.api.permissions.HasScope"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "1200/min"},
}
SPECTACULAR_SETTINGS = {
    "TITLE": "EVAC - Event and Venue Administration Core API",
    "DESCRIPTION": "REST API for events, venues, roles, modules, extensions and audit. "
    "Authenticate with a session or `Authorization: Bearer evac_...` service token.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# --------------------------------------------------------------------------- EVAC specific
# Fernet keys for secrets at rest (extension credentials, TOTP seeds). First key encrypts, all decrypt
# (rotation). Generate with ``python manage.py evac_genkey``. Empty = derived from SECRET_KEY (dev only;
# prod settings refuse to start without explicit keys).
EVAC_SECRETS_KEYS = env("EVAC_SECRETS_KEYS")
EVAC_RATE_LIMITS = {"login": 20, "twofactor": 20, "setup": 10, "webhook": 600, "invite": 20, "early_access": 10}
# Early-access gate (docs/adr/0012-early-access-gate.md): a shared password in front of the whole site while
# a public server is not ready for everyone. Empty = off. Changing the password locks everybody out again.
EVAC_EARLY_ACCESS_PASSWORD = env("EVAC_EARLY_ACCESS_PASSWORD")
EVAC_EARLY_ACCESS_DAYS = env("EVAC_EARLY_ACCESS_DAYS")
EVAC_EARLY_ACCESS_MESSAGE = env("EVAC_EARLY_ACCESS_MESSAGE")
EVAC_LOGIN_MAX_FAILURES = env("EVAC_LOGIN_MAX_FAILURES")
EVAC_LOGIN_LOCKOUT_MINUTES = env("EVAC_LOGIN_LOCKOUT_MINUTES")
EVAC_INVITATION_TTL_HOURS = env("EVAC_INVITATION_TTL_HOURS")
EVAC_WEBHOOK_TIMEOUT = env("EVAC_WEBHOOK_TIMEOUT")
EVAC_OUTBOX_MAX_ATTEMPTS = env("EVAC_OUTBOX_MAX_ATTEMPTS")

EVAC_OIDC_ENABLED = env("EVAC_OIDC_ENABLED")
EVAC_OIDC_ISSUER = env("EVAC_OIDC_ISSUER")
EVAC_OIDC_CLIENT_ID = env("EVAC_OIDC_CLIENT_ID")
EVAC_OIDC_CLIENT_SECRET = env("EVAC_OIDC_CLIENT_SECRET")
EVAC_OIDC_SCOPES = env("EVAC_OIDC_SCOPES")
EVAC_OIDC_BUTTON_LABEL = env("EVAC_OIDC_BUTTON_LABEL")
EVAC_OIDC_AUTO_CREATE = env("EVAC_OIDC_AUTO_CREATE")
EVAC_OIDC_TRUST_EMAIL_VERIFIED = env("EVAC_OIDC_TRUST_EMAIL_VERIFIED")
EVAC_OIDC_ALLOW_PASSWORD_LOGIN = env("EVAC_OIDC_ALLOW_PASSWORD_LOGIN")
# Treat an IdP login with MFA (amr claim) as two-factor verified in EVAC
EVAC_OIDC_TRUST_MFA = env("EVAC_OIDC_TRUST_MFA")
# WebAuthn relying party; empty RP ID = host of EVAC_PUBLIC_URL
EVAC_WEBAUTHN_RP_ID = env("EVAC_WEBAUTHN_RP_ID")
EVAC_WEBAUTHN_RP_NAME = env("EVAC_WEBAUTHN_RP_NAME")
SENTRY_DSN = env("SENTRY_DSN")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "std": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        "json": {"()": "apps.core.logging.JsonFormatter"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler",
                             "formatter": env("LOG_FORMAT", default="std")}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {"evac": {"level": "DEBUG" if DEBUG else "INFO"}},
}
