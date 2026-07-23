"""
Django settings for the QuestLog / Casual Heroes web app.
"""

from pathlib import Path
import os
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# An explicit environment file is required for local/staging instances. This
# prevents a test process on the production host from silently inheriting the
# production database and service credentials.
_EXPLICIT_ENV_FILE = os.getenv('QUESTLOG_ENV_FILE', '').strip()
_SECRETS_FILE = Path('/etc/casual-heroes/secrets.env')
if _EXPLICIT_ENV_FILE:
    _env_path = Path(_EXPLICIT_ENV_FILE).expanduser()
    if not _env_path.is_absolute():
        _env_path = BASE_DIR / _env_path
    if not _env_path.is_file():
        raise ImproperlyConfigured(
            f"QUESTLOG_ENV_FILE does not exist or is not a file: {_env_path}"
        )
    load_dotenv(_env_path, override=True)
elif _SECRETS_FILE.exists():
    load_dotenv(_SECRETS_FILE, override=True)
else:
    load_dotenv(BASE_DIR / '.env', override=True)

# Also load warden.env for shared bot credentials (FLUXER_BOT_TOKEN, etc.)
# Does not override anything already set by secrets.env
_WARDEN_SECRETS = Path('/etc/casual-heroes/warden.env')
if _WARDEN_SECRETS.exists():
    load_dotenv(_WARDEN_SECRETS, override=False)

QUESTLOG_ENVIRONMENT = os.getenv(
    'QUESTLOG_ENVIRONMENT', 'production'
).strip().lower()
IS_NON_PRODUCTION = QUESTLOG_ENVIRONMENT in {
    'development', 'dev', 'test', 'testing', 'staging',
}

# Defense in depth: later modules still contain legacy load_dotenv() calls.
# Keeping these keys present-but-empty stops those calls from filling missing
# values from a production .env after development settings have loaded.
if IS_NON_PRODUCTION:
    for _external_key in (
        'AMP_URL',
        'AMP_USER',
        'AMP_PASSWORD',
        'DISCORD_BOT_TOKEN',
        'DISCORD_BOT_API_TOKEN',
        'WARDEN_BOT_API_TOKEN',
        'FLUXER_BOT_TOKEN',
        'MATRIX_ACCESS_TOKEN',
        'STRIPE_SECRET_KEY',
        'STRIPE_WEBHOOK_SECRET',
        'GAME_SUGGESTION_WEBHOOK',
        'EMAIL_HOST_USER',
        'EMAIL_HOST_PASSWORD',
        'DISCORD_CLIENT_ID',
        'DISCORD_CLIENT_SECRET',
        'FLUXER_CLIENT_ID',
        'FLUXER_CLIENT_SECRET',
        'MATRIX_OIDC_CLIENT_ID',
        'MATRIX_OIDC_CLIENT_SECRET',
        'TWITCH_CLIENT_ID',
        'TWITCH_CLIENT_SECRET',
        'YOUTUBE_CLIENT_ID',
        'YOUTUBE_CLIENT_SECRET',
        'KICK_CLIENT_ID',
        'KICK_CLIENT_SECRET',
        'TURNSTILE_SITE_KEY',
        'TURNSTILE_SECRET_KEY',
    ):
        os.environ[_external_key] = ''

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY is not set. Add it to .env.")

DEBUG = False

# Public ESO pages are archived, not deleted. Keep this disabled in production;
# setting PUBLIC_ESO_ENABLED=true restores the existing routes and APIs.
PUBLIC_ESO_ENABLED = os.getenv(
    'PUBLIC_ESO_ENABLED', 'false'
).strip().lower() in {'1', 'true', 'yes', 'on'}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': '/srv/ch-webserver/cache/',
        'OPTIONS': {
            'FILE_CACHE_PERMISSIONS': 0o664,
        },
    }
}

# ---------------------------------------------------------------------------
# Domain configuration — set BASE_DOMAIN in your secrets/env file.
# Defaults to 'localhost' so the project works out of the box for development.
# ---------------------------------------------------------------------------
BASE_DOMAIN      = os.getenv('BASE_DOMAIN', 'localhost')
DASHBOARD_DOMAIN = os.getenv('DASHBOARD_DOMAIN', f'dashboard.{BASE_DOMAIN}')

# Content subdomains used by the main site (informational pages, etc.)
_CONTENT_SUBDOMAINS = [
    'gamesweplay', 'aboutus', 'privacy', 'terms',
    'contactus', 'faq', 'guides', 'reviews', 'questlog',
]

ALLOWED_HOSTS = (
    ['localhost', '127.0.0.1', BASE_DOMAIN, f'www.{BASE_DOMAIN}',
     DASHBOARD_DOMAIN, f'www.{DASHBOARD_DOMAIN}']
    + [f'{s}.{BASE_DOMAIN}' for s in _CONTENT_SUBDOMAINS]
    + [f'www.{s}.{BASE_DOMAIN}' for s in _CONTENT_SUBDOMAINS]
)
# Append any extra hosts supplied at deploy time (comma-separated)
_extra_hosts = os.getenv('EXTRA_ALLOWED_HOSTS', '')
if _extra_hosts:
    ALLOWED_HOSTS += [h.strip() for h in _extra_hosts.split(',') if h.strip()]

# CSRF Trusted Origins (REQUIRED for OAuth2 and cross-subdomain requests)
CSRF_TRUSTED_ORIGINS = (
    [f'https://{BASE_DOMAIN}', f'https://www.{BASE_DOMAIN}',
     f'https://{DASHBOARD_DOMAIN}', f'https://www.{DASHBOARD_DOMAIN}']
    + [f'https://{s}.{BASE_DOMAIN}' for s in _CONTENT_SUBDOMAINS]
)

INSTALLED_APPS = [
    'admin_tools',
    'admin_tools.theming',
    'admin_tools.menu',
    'admin_tools.dashboard',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    'csp',
    'app',
]

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

ADMIN_TOOLS_INDEX_DASHBOARD = 'core.dashboard.CustomIndexDashboard'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'app.security_middleware.SecurityMiddleware',
    'csp.middleware.CSPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'app.middleware.DashboardDomainMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'app.security_middleware.ScrapingProtectionMiddleware',
    'app.security_middleware.MaintenanceMiddleware',
    'app.pageview_middleware.PageViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'casualsite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'app', 'templates'),
            os.path.join(BASE_DIR, 'app', 'questlog_web', 'templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.debug',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'app.context_processors.subscription_info',
            ],
        },
    },
]

WSGI_APPLICATION = 'casualsite.wsgi.application'


_DJANGO_DB_PASSWORD = os.getenv('DJANGO_DB_PASSWORD')
if not _DJANGO_DB_PASSWORD:
    raise ValueError("DJANGO_DB_PASSWORD is not set. Add it to .env - refusing to fall back to an empty-password DB connection.")

_WARDEN_DB_PASSWORD = os.getenv('WARDEN_DB_PASSWORD')
if not _WARDEN_DB_PASSWORD:
    raise ValueError("WARDEN_DB_PASSWORD is not set. Add it to warden.env/.env - refusing to fall back to an empty-password DB connection.")

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DJANGO_DB_NAME', 'questlog_web'),
        'USER': os.getenv('DJANGO_DB_USER', 'django_user'),
        'PASSWORD': _DJANGO_DB_PASSWORD,
        'HOST': os.getenv('DJANGO_DB_HOST', 'localhost'),
        'PORT': os.getenv('DJANGO_DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    },
    'warden': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('WARDEN_DB_NAME', 'warden_db'),
        'USER': os.getenv('WARDEN_DB_USER', 'root'),
        'PASSWORD': _WARDEN_DB_PASSWORD,
        'HOST': os.getenv('WARDEN_DB_HOST', 'localhost'),
        'PORT': os.getenv('WARDEN_DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}

if IS_NON_PRODUCTION:
    for _alias, _config in DATABASES.items():
        _database_name = str(_config.get('NAME') or '').lower()
        if not any(
            marker in _database_name
            for marker in ('_dev', '-dev', '_test', '-test', '_staging', '-staging')
        ):
            raise ImproperlyConfigured(
                f"Refusing to start {QUESTLOG_ENVIRONMENT}: database "
                f"{_alias!r} must contain dev, test, or staging in its name."
            )

# =============================================================================
# MATRIX OIDC (Primary Auth — via MAS at sso.casual-heroes.com)
# =============================================================================
MATRIX_OIDC_AUTHORITY    = os.getenv('MATRIX_OIDC_AUTHORITY', f'https://sso.{BASE_DOMAIN}')
MATRIX_OIDC_CLIENT_ID    = os.getenv('MATRIX_OIDC_CLIENT_ID', '')
MATRIX_OIDC_CLIENT_SECRET= os.getenv('MATRIX_OIDC_CLIENT_SECRET', '')
MATRIX_OIDC_REDIRECT_URI = os.getenv('MATRIX_OIDC_REDIRECT_URI', f'https://{BASE_DOMAIN}/ql/auth/matrix/callback/')

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/ql/'
# =============================================================================
# EMAIL (Gmail SMTP via app password)
# =============================================================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', f'QuestLog <noreply@{BASE_DOMAIN}>')


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 12},
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/New_York'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
MEDIA_URL = '/media/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'app/static'),
]

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Session — cross-subdomain (leading dot covers all *.BASE_DOMAIN)
# Set SESSION_COOKIE_DOMAIN='' in your env to disable cross-subdomain cookies (e.g. local dev)
_cookie_domain = None if BASE_DOMAIN == 'localhost' else f'.{BASE_DOMAIN}'
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_NAME = 'casualheroes_session'
SESSION_COOKIE_DOMAIN = os.getenv('SESSION_COOKIE_DOMAIN', _cookie_domain)
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400 * 3  # 3 days sliding window (resets on every request via SAVE_EVERY_REQUEST)
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_PATH = '/'

CSRF_COOKIE_DOMAIN = os.getenv('CSRF_COOKIE_DOMAIN', _cookie_domain)
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = True

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Rate limiting — Cloudflare sits in front, so the real client IP is the
# first entry in X-Forwarded-For. Cloudflare's CF-Connecting-IP is also
# available but not always present in test environments.
def get_client_ip(group, request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')

RATELIMIT_KEY = get_client_ip
# Callable fallback: CF-Connecting-IP → X-Forwarded-For → REMOTE_ADDR
# Using a string header here would crash if the Cloudflare header is absent.
RATELIMIT_IP_META_KEY = lambda r: (
    r.META.get('HTTP_CF_CONNECTING_IP') or
    (r.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()) or
    r.META.get('REMOTE_ADDR', '')
)

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'app': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Non-file POST field size cap (JSON bodies, form fields — NOT multipart file data)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10MB — sufficient for any JSON payload
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024    # 5MB — spool to temp file above this

# ==============================================================================
# Content Security Policy
# ==============================================================================
# unsafe-inline / unsafe-eval needed while Tailwind JIT runs from CDN.
# Tailwind generates inline styles at runtime and its compiler needs eval().
# XSS risk is mitigated by sanitize_text() on all user input + CSRF on
# all state-changing requests. Switch to nonce-based CSP once Tailwind
# is precompiled.

CSP_DEFAULT_SRC = ("'self'",)

CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",
    "'unsafe-eval'",    # Tailwind JIT
    "https://cdn.tailwindcss.com",
    "https://unpkg.com",
    "https://cdn.jsdelivr.net",  # DOMPurify
    "https://cdnjs.cloudflare.com",
    "https://static.cloudflareinsights.com",  # Cloudflare analytics
)

CSP_STYLE_SRC = (
    "'self'",
    "'unsafe-inline'",
    "https://cdn.tailwindcss.com",
    "https://cdnjs.cloudflare.com",
)

CSP_REPORT_URI = '/csp-violations/'
CSP_REPORT_ONLY = False
CSP_IMG_SRC = (
    "'self'",
    "data:",
    "https:",
)
CSP_FONT_SRC = (
    "'self'",
    "https://cdnjs.cloudflare.com",
)
CSP_CONNECT_SRC = (
    "'self'",
    "https://cdn.jsdelivr.net",
    "https://www.youtube.com",
    "https://www.youtube-nocookie.com",
    "https://www.google.com",
    "https://docs.google.com",
)
CSP_FRAME_SRC = (
    "'self'",
    "https://www.youtube.com",
    "https://www.youtube-nocookie.com",
    "https://player.twitch.tv",
    "https://discord.com",
    "https://store.steampowered.com",
    "https://docs.google.com",
)
CSP_CHILD_SRC = (
    "'self'",
    "https://www.youtube.com",
    "https://www.youtube-nocookie.com",
    "https://player.twitch.tv",
    "https://discord.com",
    "https://store.steampowered.com",
    "https://docs.google.com",
)
CSP_MEDIA_SRC = (
    "'self'",
    "https://www.youtube.com",
    "https://www.youtube-nocookie.com",
    "https:",  # Allow media from any HTTPS source
)
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'", "https://billing.stripe.com", "https://checkout.stripe.com")

# ============================================================================
# Stripe
# ============================================================================
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')
STRIPE_TEST_MODE = os.getenv('STRIPE_TEST_MODE', 'True').lower() == 'true'
# Hero subscription: set STRIPE_HERO_PRICE_ID to the price_... ID from Stripe dashboard ($5/mo)
STRIPE_HERO_PRICE_ID = os.getenv('STRIPE_HERO_PRICE_ID', '')

CSP_SCRIPT_SRC = CSP_SCRIPT_SRC + ("https://js.stripe.com",)
CSP_FRAME_SRC = CSP_FRAME_SRC + ("https://js.stripe.com", "https://hooks.stripe.com")
CSP_CONNECT_SRC = CSP_CONNECT_SRC + ("https://api.stripe.com",) if hasattr(CSP_CONNECT_SRC, '__add__') else ("'self'", "https://api.stripe.com")

# ============================================================================
# Cloudflare Turnstile (CAPTCHA)
# ============================================================================
TURNSTILE_SITE_KEY   = os.getenv('TURNSTILE_SITE_KEY', '')
TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY', '')

CSP_SCRIPT_SRC  = CSP_SCRIPT_SRC  + ("https://challenges.cloudflare.com",)
CSP_FRAME_SRC   = CSP_FRAME_SRC   + ("https://challenges.cloudflare.com",)
CSP_STYLE_SRC   = CSP_STYLE_SRC   + ("https://challenges.cloudflare.com",)
CSP_CONNECT_SRC = CSP_CONNECT_SRC + ("https://challenges.cloudflare.com",)

# ============================================================================
# YouTube
# ============================================================================
YOUTUBE_CLIENT_ID = os.getenv('YOUTUBE_CLIENT_ID', '')
YOUTUBE_CLIENT_SECRET = os.getenv('YOUTUBE_CLIENT_SECRET', '')
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '')
YOUTUBE_CHANNEL_ID = os.getenv('YOUTUBE_CHANNEL_ID', 'UC1vrFvt7vjmRLIhOF6umSHw')
YOUTUBE_OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
]
YOUTUBE_REDIRECT_URI = os.getenv('YOUTUBE_REDIRECT_URI', f'https://{BASE_DOMAIN}/api/youtube/oauth/callback')
YOUTUBE_REDIRECT_URI_QL = os.getenv('YOUTUBE_REDIRECT_URI_QL', f'https://{BASE_DOMAIN}/ql/auth/youtube/callback/')

CSP_CONNECT_SRC = CSP_CONNECT_SRC + ("https://www.googleapis.com", "https://youtube.googleapis.com")
CSP_FRAME_SRC = CSP_FRAME_SRC + ("https://www.youtube.com", "https://www.youtube-nocookie.com")

# ============================================================================
# Discord (account linking for QuestLog web - separate from dashboard OAuth)
# ============================================================================
DISCORD_CLIENT_ID          = os.getenv('DISCORD_CLIENT_ID', '')
DISCORD_CLIENT_SECRET      = os.getenv('DISCORD_CLIENT_SECRET', '')
DISCORD_REDIRECT_URI_QL        = os.getenv('DISCORD_REDIRECT_URI_QL',        f'https://{BASE_DOMAIN}/ql/auth/discord/link/callback/')
DISCORD_REDIRECT_URI_DASHBOARD = os.getenv('DISCORD_REDIRECT_URI_DASHBOARD', f'https://{BASE_DOMAIN}/ql/auth/discord/dashboard/callback/')

# Matrix / MAS OAuth (account linking for QuestLog web)
# ============================================================================
MAS_CLIENT_ID       = os.getenv('MAS_CLIENT_ID', '')
MAS_CLIENT_SECRET   = os.getenv('MAS_CLIENT_SECRET', '')
MAS_REDIRECT_URI    = os.getenv('MAS_REDIRECT_URI', f'https://{BASE_DOMAIN}/ql/auth/matrix/callback/')
MAS_ISSUER          = os.getenv('MAS_ISSUER', 'https://sso.casual-heroes.com')
# Internal URL bypasses Cloudflare for server-to-server token/userinfo calls
MAS_INTERNAL_URL    = os.getenv('MAS_INTERNAL_URL', 'http://localhost:8181')

# Fluxer (account linking for QuestLog web)
# ============================================================================
FLUXER_CLIENT_ID           = os.getenv('FLUXER_CLIENT_ID', '')
FLUXER_CLIENT_SECRET       = os.getenv('FLUXER_CLIENT_SECRET', '')
FLUXER_REDIRECT_URI_QL         = os.getenv('FLUXER_REDIRECT_URI_QL',         f'https://{BASE_DOMAIN}/ql/auth/fluxer/link/callback/')
FLUXER_REDIRECT_URI_DASHBOARD  = os.getenv('FLUXER_REDIRECT_URI_DASHBOARD',  f'https://{BASE_DOMAIN}/ql/auth/fluxer/dashboard/callback/')

# Twitch
# ============================================================================
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID', '')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET', '')
TWITCH_REDIRECT_URI = os.getenv('TWITCH_REDIRECT_URI', f'https://{BASE_DOMAIN}/api/twitch/oauth/callback')
TWITCH_REDIRECT_URI_QL = os.getenv('TWITCH_REDIRECT_URI_QL', f'https://{BASE_DOMAIN}/ql/auth/twitch/callback/')

CSP_CONNECT_SRC = CSP_CONNECT_SRC + ("https://id.twitch.tv", "https://api.twitch.tv")
CSP_FRAME_SRC = CSP_FRAME_SRC + ("https://player.twitch.tv", "https://www.twitch.tv")

KICK_CLIENT_ID = os.getenv('KICK_CLIENT_ID', '')
KICK_CLIENT_SECRET = os.getenv('KICK_CLIENT_SECRET', '')
KICK_REDIRECT_URI_QL = os.getenv('KICK_REDIRECT_URI_QL', f'https://{BASE_DOMAIN}/ql/auth/kick/callback/')

CSP_CONNECT_SRC = CSP_CONNECT_SRC + ("https://id.kick.com", "https://api.kick.com")

# Social video embeds (TikTok, Instagram, Kick, X/Twitter)
CSP_FRAME_SRC = CSP_FRAME_SRC + (
    "https://www.tiktok.com",
    "https://www.instagram.com",
    "https://kick.com",
    "https://player.kick.com",
    "https://platform.twitter.com",
    "https://twitter.com",
    "https://x.com",
    "https://clips.twitch.tv",
)

# ============================================================================
# Encryption (Fernet, used for OAuth token storage)
# ============================================================================
# Required. App will refuse to start if missing.
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Shared secret for bot <-> web internal API authentication
BOT_INTERNAL_SECRET = os.getenv('BOT_INTERNAL_SECRET', '')
if not BOT_INTERNAL_SECRET:
    raise ImproperlyConfigured(
        "BOT_INTERNAL_SECRET is not set. Set it in /etc/casual-heroes/secrets.env."
    )
FLUXER_BOT_TOKEN   = os.getenv('FLUXER_BOT_TOKEN', '')
MATRIX_ACCESS_TOKEN = os.getenv('MATRIX_ACCESS_TOKEN', '')

# Early access gate — set EARLY_ACCESS_ENABLED=1 in secrets.env to require invite codes at registration
EARLY_ACCESS_ENABLED = os.getenv('EARLY_ACCESS_ENABLED', '') in ('1', 'true', 'yes', 'True')
FLUXER_API_BASE    = os.getenv('FLUXER_API_BASE', 'https://api.fluxer.app')
FLUXER_API_VERSION = os.getenv('FLUXER_API_VERSION', '1')

ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', '')
if not ENCRYPTION_KEY:
    raise ImproperlyConfigured(
        "ENCRYPTION_KEY is not set. Set it in /etc/casual-heroes/secrets.env. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )
