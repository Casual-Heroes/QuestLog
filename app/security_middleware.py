"""
Blocks probe requests for common attack targets before they reach Django.
Stops path traversal, WordPress scanners, config file snooping, etc.
"""
from django.core.cache import cache
from django.conf import settings
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotFound,
    JsonResponse,
)
from django.shortcuts import render
import hashlib
import logging
import os

logger = logging.getLogger(__name__)


# Public pages and APIs whose records can be cheaply enumerated. Live overlay,
# catalog-sync, authentication, and ordinary content routes are deliberately
# excluded so this protection cannot break the desktop app or OBS sources.
SCRAPE_PROTECTED_PREFIXES = (
    '/api/gamers/',
    '/api/creators/',
    '/api/communities/',
    '/api/soulslike/builds/',
    '/api/soulslike/builds/browse/',
    '/gamers/',
    '/creators/',
    '/communities/',
    '/u/',
    '/soulslike/builds/',
    '/soulslike/community-runs/',
)

# These agents explicitly identify bulk data, SEO, or AI crawlers. This is
# origin enforcement for clients that ignore robots.txt. Generic HTTP clients
# are denied only on the enumerable surfaces above, not across app APIs.
DENIED_SCRAPER_AGENTS = (
    'ahrefsbot',
    'amazonbot',
    'anthropic-ai',
    'blexbot',
    'bytespider',
    'ccbot',
    'chatgpt-user',
    'claude-web',
    'claudebot',
    'cohere-ai',
    'dataforseobot',
    'diffbot',
    'dotbot',
    'gptbot',
    'imagesiftbot',
    'meta-externalagent',
    'mj12bot',
    'omgilibot',
    'perplexitybot',
    'petalbot',
    'semrushbot',
    'serpstatbot',
    'youbot',
)

GENERIC_AUTOMATION_AGENTS = (
    'aiohttp',
    'curl/',
    'go-http-client',
    'httpx/',
    'libwww-perl',
    'python-requests',
    'scrapy',
    'wget/',
)

# Verified-bot status is best enforced by Cloudflare. At origin, allow the
# search/social preview agents the site intentionally supports.
TRUSTED_PUBLIC_AGENTS = (
    'applebot',
    'bingbot',
    'discordbot',
    'duckduckbot',
    'facebookexternalhit',
    'googlebot',
    'linkedinbot',
    'slackbot',
    'telegrambot',
    'twitterbot',
)


class ScrapingProtectionMiddleware:
    """
    Add origin-side friction to bulk enumeration without hiding public pages.

    - Known scraper/automation user agents are denied on directory surfaces.
    - Anonymous clients share a conservative per-IP request budget.
    - Authenticated humans and intentional search/social crawlers are exempt.
    - JSON APIs receive no-index headers so search engines do not index raw
      records alongside their human-facing pages.

    Cloudflare Bot Fight Mode and edge rate limiting remain the first line of
    defense; this middleware is a fail-safe when traffic reaches the origin.
    """

    WINDOW_SECONDS = max(
        10, int(os.getenv('SCRAPE_RATE_WINDOW_SECONDS', '60'))
    )
    ANONYMOUS_REQUEST_LIMIT = max(
        5, int(os.getenv('SCRAPE_RATE_LIMIT', '30'))
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.lower()
        method = request.method.upper()

        if method in ('GET', 'HEAD') and self._is_protected(path):
            user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
            trusted_agent = any(
                agent in user_agent for agent in TRUSTED_PUBLIC_AGENTS
            )

            if not trusted_agent and self._is_automation(user_agent):
                logger.warning(
                    "Blocked scraper user-agent from %s on %s",
                    self._client_ip(request),
                    request.path,
                )
                return self._blocked_response(path)

            if not trusted_agent and not self._is_authenticated(request):
                retry_after = self._consume_anonymous_budget(request)
                if retry_after is not None:
                    logger.warning(
                        "Rate-limited anonymous enumeration from %s on %s",
                        self._client_ip(request),
                        request.path,
                    )
                    return self._rate_limited_response(path, retry_after)

        response = self.get_response(request)
        if method in ('GET', 'HEAD') and path.startswith('/api/'):
            response['X-Robots-Tag'] = 'noindex, nofollow, nosnippet'
        return response

    @staticmethod
    def _is_protected(path):
        return any(path.startswith(prefix) for prefix in SCRAPE_PROTECTED_PREFIXES)

    @staticmethod
    def _is_automation(user_agent):
        return any(agent in user_agent for agent in (
            DENIED_SCRAPER_AGENTS + GENERIC_AUTOMATION_AGENTS
        ))

    @staticmethod
    def _is_authenticated(request):
        try:
            return bool(
                request.session.get('web_user_id')
                or request.user.is_authenticated
            )
        except (AttributeError, TypeError):
            return False

    def _consume_anonymous_budget(self, request):
        ip = self._client_ip(request)
        digest = hashlib.sha256(ip.encode('utf-8')).hexdigest()[:24]
        key = f'scrape-budget:{digest}'
        try:
            if cache.add(key, 1, timeout=self.WINDOW_SECONDS):
                count = 1
            else:
                count = cache.incr(key)
        except (ValueError, TypeError):
            # A cache expiry race can remove the key between add() and incr().
            cache.set(key, 1, timeout=self.WINDOW_SECONDS)
            count = 1
        if count > self.ANONYMOUS_REQUEST_LIMIT:
            return self.WINDOW_SECONDS
        return None

    @staticmethod
    def _client_ip(request):
        return (
            request.META.get('HTTP_CF_CONNECTING_IP', '').strip()
            or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', '')
            or 'unknown'
        )

    @staticmethod
    def _blocked_response(path):
        if path.startswith('/api/'):
            response = JsonResponse({'error': 'Automated access denied'}, status=403)
        else:
            response = HttpResponseForbidden('Automated access denied')
        response['X-Robots-Tag'] = 'noindex, nofollow, nosnippet'
        return response

    @staticmethod
    def _rate_limited_response(path, retry_after):
        if path.startswith('/api/'):
            response = JsonResponse(
                {'error': 'Too many directory requests; please try again shortly'},
                status=429,
            )
        else:
            response = HttpResponse(
                'Too many requests; please try again shortly',
                status=429,
                content_type='text/plain',
            )
        response['Retry-After'] = str(retry_after)
        response['X-Robots-Tag'] = 'noindex, nofollow, nosnippet'
        return response

# Maintenance mode flag file - if this file exists, the site is in maintenance mode
# Override with MAINTENANCE_FLAG env var for custom deployment paths
import pathlib as _pathlib
MAINTENANCE_FLAG = os.getenv(
    'MAINTENANCE_FLAG',
    str(_pathlib.Path(__file__).resolve().parent.parent / '.maintenance')
)

# Paths that bypass maintenance mode (admin + auth always accessible).
# request.path always has a leading slash, so every prefix here must too, or
# the startswith() check below silently never matches (a bare 'admin' does
# not match '/admin/...') and the path stays blocked during maintenance
# despite looking exempt.
MAINTENANCE_EXEMPT_PREFIXES = [
    '/admin',          # admin panel + admin API
    '/api/admin',
    '/admin-login',    # hardened admin-only login (replaces login)
    '/auth',           # OAuth callbacks (Steam etc.)
    '/verify-email',
    '/api/igdb/',      # public read-only game search - no reason to block
    # 'login',        # disabled - public login removed in closed-access mode
    # '/login/',          # disabled - public login removed in closed-access mode
    '/logout/',
    '/static/',
    '/media/',
    '/questchat/',
    '/qc/',            # QuestChat bridge API - app stays accessible during maintenance
    '/auth/discord/',     # Discord OAuth flow must complete before we can check identity
    '/questlog/login/',   # Discord OAuth entry point - must be reachable to initiate auth
]

# Dashboard paths only the bot owner / site admin can access during maintenance
DASHBOARD_PREFIXES = [
    '/questlog/',
    '/dashboard/',
]

BOT_OWNER_ID = os.getenv('BOT_OWNER_ID', '')


class MaintenanceMiddleware:
    """
    If .maintenance flag file exists, serve 503 maintenance page for all
    public paths. Site admins always get full access to review changes.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.path.exists(MAINTENANCE_FLAG):
            # Site admins always get full access during maintenance.
            # Re-validate against DB on each request - session flag alone is not
            # sufficient because admin status may have changed since login.
            if request.session.get('web_user_is_admin') and request.session.get('web_user_id'):
                user_id = request.session['web_user_id']
                try:
                    from app.db import get_db_session
                    from app.questlog_web.models import WebUser as _WU
                    with get_db_session() as _db:
                        _u = _db.query(_WU).filter_by(
                            id=user_id, is_admin=True, is_banned=False, is_disabled=False
                        ).first()
                    if _u:
                        return self.get_response(request)
                except Exception:
                    pass  # on any DB error, fall through to maintenance page

            path = request.path

            # Standard exempt paths (auth callbacks, static, etc.)
            if any(path.startswith(p) for p in MAINTENANCE_EXEMPT_PREFIXES):
                return self.get_response(request)

            # Discord bot dashboard - only the bot owner can access during maintenance
            if any(path.startswith(p) for p in DASHBOARD_PREFIXES):
                discord_user = request.session.get('discord_user', {})
                discord_id = str(discord_user.get('id', ''))
                if BOT_OWNER_ID and discord_id == BOT_OWNER_ID:
                    # Re-validate against DB to prevent session spoofing
                    try:
                        from app.db import get_db_session
                        from sqlalchemy import text as sa_text
                        with get_db_session() as _db:
                            _row = _db.execute(
                                sa_text("SELECT id FROM web_users WHERE discord_id=:did AND is_admin=1 AND is_banned=0 AND is_disabled=0 LIMIT 1"),
                                {'did': discord_id}
                            ).fetchone()
                            if _row:
                                return self.get_response(request)
                    except Exception:
                        pass  # fall through to deny if DB check fails
                # Not the owner - send to maintenance page (not Discord login)
                response = render(request, 'questlog_web/maintenance.html', status=503)
                response['Retry-After'] = '3600'
                return response

            response = render(request, 'questlog_web/maintenance.html', status=503)
            response['Retry-After'] = '3600'
            return response
        return self.get_response(request)


BLOCKED_PATTERNS = [
    # Config / secrets
    '.env', '.git', '.svn', '.hg', '.DS_Store',
    'web.config', 'htaccess', 'htpasswd',
    '.bak', '.backup', '.old', '.save', '.swp', '.tmp',
    'config.php', 'wp-config.php', 'configuration.php',
    'credentials', 'secrets',
    '.npmrc', '.dockerenv', 'docker-compose',
    'id_rsa', 'id_dsa', 'authorized_keys',
    'database.yml', 'settings.py.bak',

    # WordPress
    'wp-login', 'wp-admin', 'wp-content', 'wp-includes',
    'xmlrpc.php', 'wp-cron.php', 'wp-config',

    # PHP shells / admin panels
    'phpinfo', 'phpmyadmin', 'pma', 'admin.php',
    'shell.php', 'c99.php', 'r57.php', 'backdoor.php',

    # Java / .NET frameworks
    'solr/admin', 'jenkins', 'struts',
    'console/', 'actuator/', 'jmx-console',
    'manager/html', 'tomcat',

    # ColdFusion
    'cfide', 'cfide/', 'administrator/login',
    'cfformgateway', 'railo-context',

    # API spec probing
    'graphql', 'swagger', 'api-docs',

    # Misc well-known probes
    '.well-known/discord',
]

BLOCKED_DIRS = [
    '../', '..\\', '%2e%2e/', '%2e%2e\\',
    '..%2f', '..%5c', '%252e%252e',
]


class SecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.lower()

        # ESO is archived rather than deleted. Block every public page and API
        # before URL resolution while leaving the admin review API available.
        if not settings.PUBLIC_ESO_ENABLED and (
            path == '/eso'
            or path.startswith('/eso/')
            or path.startswith('/api/eso/')
        ):
            response = HttpResponseNotFound()
            response['X-Robots-Tag'] = 'noindex, nofollow, nosnippet'
            return response

        for pattern in BLOCKED_PATTERNS:
            if pattern in path:
                logger.warning(f"Blocked probe from {self._client_ip(request)}: {request.path}")
                return HttpResponseNotFound()

        for pattern in BLOCKED_DIRS:
            if pattern in request.path or pattern in path:
                logger.warning(f"Blocked traversal from {self._client_ip(request)}: {request.path}")
                return HttpResponseNotFound()

        response = self.get_response(request)
        response['Permissions-Policy'] = (
            'camera=(), microphone=(), geolocation=(), payment=(), usb=(), '
            'interest-cohort=()'
        )
        response['X-Content-Type-Options'] = 'nosniff'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    @staticmethod
    def _client_ip(request):
        cf_ip = request.META.get('HTTP_CF_CONNECTING_IP', '').strip()
        if cf_ip:
            return cf_ip
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '?')
