"""Isolated settings for local and loopback-only QuestLog development."""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F401,F403


if not IS_NON_PRODUCTION:
    raise ImproperlyConfigured(
        "casualsite.settings_dev requires QUESTLOG_ENVIRONMENT=development, "
        "test, or staging."
    )

DEBUG = True

ALLOWED_HOSTS = [
    '127.0.0.1',
    'localhost',
    'testserver',
]
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8001',
    'http://localhost:8001',
    'https://127.0.0.1:5443',
    'https://localhost:5443',
]

SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_DOMAIN = None
CSRF_COOKIE_SECURE = False

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = 'SAMEORIGIN'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'QuestLog Development <dev-null@localhost>'

_dev_state_root = Path(
    os.getenv('QUESTLOG_DEV_STATE_ROOT', BASE_DIR / '.dev-state')
)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(_dev_state_root / 'cache'),
    }
}
STATIC_ROOT = str(_dev_state_root / 'staticfiles')
MEDIA_ROOT = str(_dev_state_root / 'media')

# Exposed as a single policy flag for new integrations. Existing integrations
# are also neutralized by blank credentials in the base settings module.
OUTBOUND_MUTATIONS_ENABLED = False
