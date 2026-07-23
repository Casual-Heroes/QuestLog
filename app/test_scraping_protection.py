from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from app.security_middleware import (
    ScrapingProtectionMiddleware,
    SecurityMiddleware,
)
from app.views import robots_txt


@override_settings(CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'scraping-protection-tests',
    },
})
class ScrapingProtectionMiddlewareTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.downstream_calls = 0

        def get_response(_request):
            self.downstream_calls += 1
            return HttpResponse('ok')

        self.middleware = ScrapingProtectionMiddleware(get_response)

    def request(self, path, *, user_agent='Mozilla/5.0', authenticated=False):
        request = self.factory.get(path, HTTP_USER_AGENT=user_agent)
        request.session = {'web_user_id': 7} if authenticated else {}
        request.user = SimpleNamespace(is_authenticated=authenticated)
        return request

    def test_known_scraper_is_denied_on_public_directory_api(self):
        response = self.middleware(self.request(
            '/api/gamers/',
            user_agent='python-requests/2.32',
        ))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.downstream_calls, 0)
        self.assertEqual(
            response['X-Robots-Tag'],
            'noindex, nofollow, nosnippet',
        )

    def test_desktop_catalog_sync_is_not_in_scraping_scope(self):
        response = self.middleware(self.request(
            '/api/soulslike/data/manifest/',
            user_agent='python-requests/2.32',
        ))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.downstream_calls, 1)

    def test_anonymous_directory_enumeration_is_rate_limited(self):
        with patch.object(
            ScrapingProtectionMiddleware,
            'ANONYMOUS_REQUEST_LIMIT',
            2,
        ):
            first = self.middleware(self.request('/api/creators/'))
            second = self.middleware(self.request('/api/creators/'))
            blocked = self.middleware(self.request('/api/creators/'))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked['Retry-After'], '60')
        self.assertEqual(self.downstream_calls, 2)

    def test_authenticated_user_bypasses_anonymous_budget(self):
        with patch.object(
            ScrapingProtectionMiddleware,
            'ANONYMOUS_REQUEST_LIMIT',
            1,
        ):
            responses = [
                self.middleware(self.request(
                    '/api/soulslike/builds/browse/',
                    authenticated=True,
                ))
                for _ in range(3)
            ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])

    def test_trusted_search_agent_bypasses_anonymous_budget(self):
        with patch.object(
            ScrapingProtectionMiddleware,
            'ANONYMOUS_REQUEST_LIMIT',
            1,
        ):
            responses = [
                self.middleware(self.request(
                    '/creators/',
                    user_agent='Mozilla/5.0 (compatible; Googlebot/2.1)',
                ))
                for _ in range(3)
            ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])

    def test_successful_json_api_response_is_not_indexable(self):
        response = self.middleware(self.request('/api/health/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['X-Robots-Tag'],
            'noindex, nofollow, nosnippet',
        )

    def test_live_robots_route_serves_canonical_hardened_policy(self):
        response = robots_txt(self.factory.get('/robots.txt'))
        body = response.content.decode('utf-8')

        self.assertIn('Disallow: /api/', body)
        self.assertIn(
            'Content-Signal: search=yes, ai-input=no, ai-train=no',
            body,
        )
        self.assertIn('User-agent: GPTBot\nDisallow: /', body)
        self.assertEqual(response['Cache-Control'], 'public, max-age=3600')


class ArchivedEsoVisibilityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.downstream_calls = 0

        def get_response(_request):
            self.downstream_calls += 1
            return HttpResponse('ok')

        self.middleware = SecurityMiddleware(get_response)

    @override_settings(PUBLIC_ESO_ENABLED=False)
    def test_public_eso_pages_and_apis_are_hidden(self):
        for path in (
            '/eso',
            '/eso/',
            '/eso/builds/',
            '/eso/apply/',
            '/api/eso/server-status/',
            '/api/eso/apply/',
            '/api/eso/builds/1/vote/',
        ):
            with self.subTest(path=path):
                response = self.middleware(self.factory.get(path))
                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response['X-Robots-Tag'],
                    'noindex, nofollow, nosnippet',
                )

        self.assertEqual(self.downstream_calls, 0)

    @override_settings(PUBLIC_ESO_ENABLED=False)
    def test_eso_admin_archive_remains_available(self):
        response = self.middleware(
            self.factory.get('/api/admin/eso/applications/')
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.downstream_calls, 1)

    @override_settings(PUBLIC_ESO_ENABLED=True)
    def test_eso_can_be_reenabled_without_restoring_data(self):
        response = self.middleware(self.factory.get('/eso/'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.downstream_calls, 1)

    def test_public_navigation_has_no_eso_entry_points(self):
        for relative_path in (
            'app/templates/base.html',
            'app/templates/questlog/base_guild.html',
            'app/questlog_web/templates/questlog_web/base_web.html',
            'app/questlog_web/templates/questlog_web/fluxer_base_guild.html',
            'app/questlog_web/templates/questlog_web/partials/web_sidebar.html',
            'app/questlog_web/templates/questlog_web/getting_started.html',
        ):
            with self.subTest(path=relative_path):
                content = (
                    Path(settings.BASE_DIR) / relative_path
                ).read_text(encoding='utf-8').lower()
                self.assertNotIn('/eso', content)
                self.assertNotIn('elder scrolls online', content)

    def test_first_party_game_catalog_and_guild_choices_exclude_eso(self):
        from app.views import DISCORD_GAMES, DISCORD_GAME_STATIC_INFO
        from app.questlog_web.views_discovery import VALID_GUILD_GAMES

        self.assertNotIn('ESO', DISCORD_GAME_STATIC_INFO)
        self.assertNotIn('ESO', {game['id'] for game in DISCORD_GAMES})
        self.assertNotIn('eso', VALID_GUILD_GAMES)
