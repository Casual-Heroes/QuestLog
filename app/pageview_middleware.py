"""
Lightweight page view tracker middleware.
Tracks: section, path, UTM params, referrer, new vs returning visitor.
Async-safe: writes are fire-and-forget via a background thread pool.
"""
import time
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='pageview')

# Map URL prefix → section label. Order matters - first match wins.
SECTION_MAP = [
    ('/soulslike/tracker',  'soulslike_tracker'),
    ('/soulslike',          'soulslike'),
    ('/ffxiv/tools',        'ffxiv_tools'),
    ('/ffxiv',              'ffxiv'),
    ('/eso',                'eso'),
    ('/indie-heroes',       'indie_heroes'),
    ('/lfg',                'lfg'),
    ('/gamesweplay',        'games_we_play'),
    ('/gameservers',        'game_servers'),
    ('/communities',        'communities'),
    ('/discover',           'discover'),
    ('/blog',               'blog'),
    ('/creators',           'creators'),
    ('/steamquest',         'steamquest'),
    ('/leaderboard',        'leaderboard'),
    ('/u/',                 'profile'),
    ('/register',           'register'),
    ('/getting-started',    'getting_started'),
    ('/feed',               'feed'),
]

SKIP_PREFIXES = (
    '/api/', '/static/', '/media/', '/admin/', '/ql/api/',
    '/internal/', '/favicon', '/__debug__', '/ws/',
)

BOT_AGENTS = (
    'bot', 'crawler', 'spider', 'curl', 'wget', 'python-requests',
    'googlebot', 'bingbot', 'slurp', 'duckduckbot', 'facebookexternalhit',
    'semrush', 'ahrefs', 'mj12bot', 'dotbot',
)

# Referrer host → source label
REFERRER_SOURCES = [
    ('discord.com',      'discord'),
    ('discord.gg',       'discord'),
    ('reddit.com',       'reddit'),
    ('old.reddit.com',   'reddit'),
    ('twitter.com',      'twitter'),
    ('x.com',            'twitter'),
    ('t.co',             'twitter'),
    ('youtube.com',      'youtube'),
    ('youtu.be',         'youtube'),
    ('twitch.tv',        'twitch'),
    ('google.',          'google'),
    ('bing.com',         'bing'),
    ('duckduckgo.com',   'duckduckgo'),
    ('facebook.com',     'facebook'),
    ('instagram.com',    'instagram'),
    ('tiktok.com',       'tiktok'),
    ('bluesky.social',   'bluesky'),
    ('bsky.app',         'bluesky'),
    ('fluxer.gg',        'fluxer'),
    ('fluxer.app',       'fluxer'),
]

OWNED_DOMAINS = ('questlog.casual-heroes.com', 'casual-heroes.com', 'dashboard.casual-heroes.com')

# Cookie name for returning visitor detection
VISITOR_COOKIE = 'ql_vid'
VISITOR_COOKIE_MAX_AGE = 365 * 24 * 3600  # 1 year


def _classify_path(path):
    for prefix, label in SECTION_MAP:
        if path.startswith(prefix):
            return label
    return None


def _classify_referrer(referrer):
    """Return (source, medium) from referrer URL."""
    if not referrer:
        return 'direct', 'none'
    try:
        host = urlparse(referrer).netloc.lower().lstrip('www.')
        if any(host == d or host.endswith('.' + d) for d in OWNED_DOMAINS):
            return 'internal', 'internal'
        for pattern, source in REFERRER_SOURCES:
            if pattern in host:
                if source in ('google', 'bing', 'duckduckgo'):
                    return source, 'organic'
                return source, 'referral'
        return host[:100] or 'unknown', 'referral'
    except Exception:
        return 'unknown', 'referral'


def _write_view(path, section, ip, user_id, referrer, utm_source, utm_medium,
                utm_campaign, is_new_visitor):
    try:
        from app.db import get_engine
        from sqlalchemy import text
        ip_hash = hashlib.sha256(ip.encode()).hexdigest() if ip else None
        now = int(time.time())
        with get_engine().connect() as conn:
            conn.execute(text("""
                INSERT INTO web_page_views
                  (section, path, ip_hash, user_id, referrer, utm_source,
                   utm_medium, utm_campaign, is_new_visitor, created_at)
                VALUES
                  (:section, :path, :ip_hash, :user_id, :referrer, :utm_source,
                   :utm_medium, :utm_campaign, :is_new_visitor, :created_at)
            """), {
                'section': section,
                'path': path[:500],
                'ip_hash': ip_hash,
                'user_id': user_id,
                'referrer': referrer[:500] if referrer else None,
                'utm_source': utm_source,
                'utm_medium': utm_medium,
                'utm_campaign': utm_campaign,
                'is_new_visitor': 1 if is_new_visitor else 0,
                'created_at': now,
            })
            conn.commit()
    except Exception:
        pass


class PageViewMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only track successful GET page views
        if (request.method != 'GET'
                or response.status_code not in (200,)
                or response.get('Content-Type', '').startswith('application/json')):
            return response

        path = request.path

        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return response

        ua = request.META.get('HTTP_USER_AGENT', '').lower()
        if any(b in ua for b in BOT_AGENTS):
            return response

        section = _classify_path(path)
        if not section:
            return response

        # IP
        ip = (request.META.get('HTTP_CF_CONNECTING_IP')
              or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
              or request.META.get('REMOTE_ADDR', ''))

        # QuestLog user_id
        user_id = None
        try:
            user_id = request.session.get('web_user_id')
        except Exception:
            pass

        # Referrer
        raw_referrer = request.META.get('HTTP_REFERER', '')
        ref_source, ref_medium = _classify_referrer(raw_referrer)

        # UTM params override referrer classification
        utm_source = request.GET.get('utm_source', '').strip()[:100] or ref_source
        utm_medium = request.GET.get('utm_medium', '').strip()[:100] or ref_medium
        utm_campaign = request.GET.get('utm_campaign', '').strip()[:100] or None

        # New vs returning visitor via cookie
        is_new_visitor = VISITOR_COOKIE not in request.COOKIES

        # Set visitor cookie on response if new
        if is_new_visitor:
            response.set_cookie(
                VISITOR_COOKIE, '1',
                max_age=VISITOR_COOKIE_MAX_AGE,
                httponly=True,
                samesite='Lax',
                secure=True,
            )

        # Fire and forget
        _executor.submit(
            _write_view, path, section, ip, user_id,
            raw_referrer or None, utm_source, utm_medium, utm_campaign, is_new_visitor
        )

        return response
