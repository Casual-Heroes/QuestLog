import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from app.questlog_web.views_pages import api_sl_err_enkindling


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _EnkindlingDb:
    def execute(self, statement):
        if 'sl_err_enkindling_system' in str(statement):
            return _Rows([('system', 'description')])
        return _Rows([
            (
                'Enduring', 'Endurance', 'old common text', '', '',
                '{"type":"equip_load_mult","value":9.99}', None, None,
            ),
        ])


@contextmanager
def _enkindling_session():
    yield _EnkindlingDb()


class SoulslikeDesktopRouteTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_desktop_build_collection_route(self):
        match = resolve('/api/soulslike/desktop/builds/')
        self.assertEqual(match.url_name, 'api_sl_builds_desktop')

    def test_desktop_build_detail_accepts_numeric_id(self):
        match = resolve('/api/soulslike/desktop/builds/11/')
        self.assertEqual(match.url_name, 'api_sl_build_detail_desktop')
        self.assertEqual(match.kwargs['build_ref'], '11')

    def test_desktop_build_detail_accepts_share_token(self):
        match = resolve('/api/soulslike/desktop/builds/MlVgxXshnxZO2w/')
        self.assertEqual(match.url_name, 'api_sl_build_detail_desktop')
        self.assertEqual(match.kwargs['build_ref'], 'MlVgxXshnxZO2w')

    def test_desktop_delete_route_remains_separate(self):
        match = resolve('/api/soulslike/desktop/builds/11/delete/')
        self.assertEqual(match.url_name, 'api_sl_build_delete_desktop')
        self.assertEqual(match.kwargs['build_id'], 11)

    def test_err_enkindling_routes_are_registered(self):
        self.assertEqual(
            resolve('/api/soulslike/err/enkindling/').url_name,
            'api_sl_err_enkindling',
        )
        self.assertEqual(
            resolve('/api/soulslike/err/enkindling/eligible/').url_name,
            'api_sl_err_enkindling_eligible',
        )

    def test_desktop_profile_includes_saved_enkindling(self):
        source = (
            Path(__file__).parent / 'questlog_web/views_pages.py'
        ).read_text(encoding='utf-8')
        self.assertIn('_PROFILE_ENKINDLE_COLS', source)
        self.assertIn("'rh1_enkindle_affix': r[52]", source)
        self.assertIn("'lh3_enkindle_rarity': r[63]", source)

    def test_live_enkindling_descriptions_use_regulation_calculator_values(self):
        request = self.factory.get('/api/soulslike/err/enkindling/')
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=_enkindling_session,
        ):
            response = api_sl_err_enkindling(request)

        payload = json.loads(response.content)
        self.assertEqual(payload['affixes'][0]['tiers'][0]['text'], 'old common text')
        self.assertEqual(
            payload['affixes'][0]['tiers'][0]['static_effect'],
            {'type': 'equip_load_mult', 'value': 1.02},
        )
