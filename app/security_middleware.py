"""
Blocks probe requests for common attack targets before they reach Django.
Stops path traversal, WordPress scanners, config file snooping, etc.
"""
from django.http import HttpResponseNotFound
from django.shortcuts import render
import logging
import os

logger = logging.getLogger(__name__)

# Maintenance mode flag file — if this file exists, the site is in maintenance mode
# Override with MAINTENANCE_FLAG env var for custom deployment paths
import pathlib as _pathlib
MAINTENANCE_FLAG = os.getenv(
    'MAINTENANCE_FLAG',
    str(_pathlib.Path(__file__).resolve().parent.parent / '.maintenance')
)

# Paths that bypass maintenance mode (admin + auth always accessible)
MAINTENANCE_EXEMPT_PREFIXES = [
    '/ql/admin',          # admin panel + admin API
    '/ql/api/admin',
    '/ql/admin-login',    # hardened admin-only login (replaces /ql/login)
    '/ql/auth',           # OAuth callbacks (Steam etc.)
    '/ql/verify-email',
    '/ql/api/igdb/',      # public read-only game search — no reason to block
    # '/ql/login',        # disabled — public login removed in closed-access mode
    # '/login/',          # disabled — public login removed in closed-access mode
    '/logout/',
    '/static/',
    '/media/',
    '/questchat/',
    '/auth/discord/',     # Discord OAuth flow must complete before we can check identity
    '/questlog/login/',   # Discord OAuth entry point — must be reachable to initiate auth
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

            # Discord bot dashboard — only the bot owner can access during maintenance
            if any(path.startswith(p) for p in DASHBOARD_PREFIXES):
                discord_user = request.session.get('discord_user', {})
                discord_id = str(discord_user.get('id', ''))
                if BOT_OWNER_ID and discord_id == BOT_OWNER_ID:
                    return self.get_response(request)
                # Not the owner — send to maintenance page (not Discord login)
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

        # Block the Django admin entirely (except admin_tools assets)
        if path.startswith('/admin/') and not path.startswith('/admin/analytics') and not path.startswith('/admin_tools/'):
            logger.warning(f"Blocked Django admin access from {self._client_ip(request)}: {request.path}")
            return HttpResponseNotFound()

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
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['X-XSS-Protection'] = '1; mode=block'
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
