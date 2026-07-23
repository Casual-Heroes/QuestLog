import hashlib
import json
import math
from contextlib import contextmanager
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from app.questlog_web.views_soulslike_data import (
    api_sl_data_download,
    api_sl_data_handoff,
    api_sl_data_manifest,
    api_sl_data_reference_client,
)


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _BossDb:
    def execute(self, statement, params):
        mode = params['mode']
        if mode == 'err':
            return _Rows([(
                'Margit (Stormveil Castle)', 'Margit', 'Stormveil Castle',
                'Limgrave', 'great_enemy',
            )])
        return _Rows([(
            'Godrick (Stormveil Castle)', 'Godrick', 'Stormveil Castle',
            'Limgrave', 'demigod',
        )])


@contextmanager
def _fake_session():
    yield _BossDb()


class SoulslikeDataSyncTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_public_routes_are_registered(self):
        self.assertEqual(
            resolve('/api/soulslike/data/manifest/').url_name,
            'api_sl_data_manifest',
        )
        self.assertEqual(
            resolve('/api/soulslike/data/bosses_err/abc/').url_name,
            'api_sl_data_download',
        )
        self.assertEqual(
            resolve('/api/soulslike/data/handoff/').url_name,
            'api_sl_data_handoff',
        )
        self.assertEqual(
            resolve('/api/soulslike/data/reference-client/').url_name,
            'api_sl_data_reference_client',
        )

    def test_manifest_advertises_content_addressed_public_datasets(self):
        request = self.factory.get('/api/soulslike/data/manifest/')
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            response = api_sl_data_manifest(request)

        payload = json.loads(response.content)
        self.assertFalse(payload['account_required'])
        self.assertEqual(payload['api_version'], 1)
        self.assertEqual(payload['schema_version'], 1)
        self.assertEqual(payload['calculation_contract_version'], 1)
        self.assertEqual(
            set(payload['datasets']),
            {
                'vanilla_calculations',
                'err_calculations',
                'bosses_err',
                'bosses_vanilla',
            },
        )
        for name, dataset in payload['datasets'].items():
            self.assertEqual(dataset['revision'], dataset['sha256'])
            self.assertEqual(len(dataset['sha256']), 64)
            self.assertIn(f'/data/{name}/{dataset["sha256"]}/', dataset['url'])
            self.assertGreater(dataset['bytes'], 0)
        self.assertEqual(response['Access-Control-Allow-Origin'], '*')
        self.assertIn('must-revalidate', response['Cache-Control'])
        self.assertIn('weapons_err', payload['live_resources'])
        self.assertIn('weapons_vanilla', payload['live_resources'])
        self.assertIn('fortunes_err', payload['live_resources'])
        self.assertIn('enkindling_err', payload['live_resources'])
        self.assertTrue(
            payload['developer_handoff']['documentation_url'].endswith(
                '/api/soulslike/data/handoff/'
            )
        )
        self.assertTrue(
            payload['developer_handoff']['reference_client_url'].endswith(
                '/api/soulslike/data/reference-client/'
            )
        )

    def test_developer_handoff_and_reference_client_are_public(self):
        handoff_request = self.factory.get('/api/soulslike/data/handoff/')
        handoff = api_sl_data_handoff(handoff_request)
        self.assertEqual(handoff.status_code, 200)
        self.assertTrue(handoff['Content-Type'].startswith('text/markdown'))
        self.assertEqual(handoff['Access-Control-Allow-Origin'], '*')
        self.assertIn(b'/api/soulslike/data/manifest/', handoff.content)

        reference_request = self.factory.get(
            '/api/soulslike/data/reference-client/'
        )
        reference = api_sl_data_reference_client(reference_request)
        self.assertEqual(reference.status_code, 200)
        self.assertTrue(reference['Content-Type'].startswith('text/x-python'))
        self.assertIn(b'class CatalogStore', reference.content)
        self.assertIn(b'Only JSON is downloaded', reference.content)

        conditional_request = self.factory.get(
            '/api/soulslike/data/handoff/',
            HTTP_IF_NONE_MATCH=handoff['ETag'],
        )
        conditional = api_sl_data_handoff(conditional_request)
        self.assertEqual(conditional.status_code, 304)

    def test_download_hash_matches_manifest_and_payload(self):
        manifest_request = self.factory.get('/api/soulslike/data/manifest/')
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            manifest_response = api_sl_data_manifest(manifest_request)
        manifest = json.loads(manifest_response.content)
        revision = manifest['datasets']['bosses_err']['revision']

        request = self.factory.get(
            f'/api/soulslike/data/bosses_err/{revision}/'
        )
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            response = api_sl_data_download(request, 'bosses_err', revision)

        self.assertEqual(hashlib.sha256(response.content).hexdigest(), revision)
        payload = json.loads(response.content)
        self.assertEqual(payload['schema_version'], 1)
        self.assertEqual(payload['mode'], 'err')
        keys = {boss['key'] for boss in payload['bosses']}
        self.assertIn('Margit (Stormveil Castle)', keys)
        self.assertIn(
            'Alabaster Lord (East of the Church of the Plague)', keys
        )
        self.assertIn('immutable', response['Cache-Control'])

    def test_etag_returns_not_modified(self):
        request = self.factory.get('/api/soulslike/data/manifest/')
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            first = api_sl_data_manifest(request)

        conditional = self.factory.get(
            '/api/soulslike/data/manifest/',
            HTTP_IF_NONE_MATCH=first['ETag'],
        )
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            second = api_sl_data_manifest(conditional)

        self.assertEqual(second.status_code, 304)
        self.assertEqual(second['ETag'], first['ETag'])

    def test_err_calculation_bundle_contains_regulation_inputs(self):
        manifest_request = self.factory.get('/api/soulslike/data/manifest/')
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            manifest_response = api_sl_data_manifest(manifest_request)
        manifest = json.loads(manifest_response.content)
        metadata = manifest['datasets']['err_calculations']

        request = self.factory.get(metadata['url'])
        response = api_sl_data_download(
            request, 'err_calculations', metadata['revision']
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['calculation_contract_version'], 1)
        self.assertEqual(payload['regulation_version'], '2.2.9.5')
        regulation = payload['payload']
        self.assertGreaterEqual(len(regulation['weapons']), 500)
        self.assertGreaterEqual(len(regulation['armor']), 700)
        self.assertEqual(
            regulation['weapons']['Ruins Greatsword']['Standard']['weight'],
            15.5,
        )
        self.assertIn('vigor_hp', regulation['derived_curves'])
        enkindling = regulation['enkindling']
        self.assertEqual(enkindling['reference_version'], '2.2.9.5')
        self.assertEqual(
            enkindling['rarity_tiers'],
            {'common': 1, 'rare': 2, 'legendary': 3},
        )
        self.assertEqual(
            enkindling['affixes']['Smoldering']['1'],
            {
                'type': 'hp_fp_stamina_mult',
                'hp': 1.02,
                'fp': 1.03,
                'stamina': 1.04,
            },
        )
        self.assertEqual(
            enkindling['affixes']['Astral']['1']['damage_type'],
            'magic',
        )
        viridian = regulation['talismans']['Viridian Amber Medallion']
        self.assertEqual(
            viridian['modifiers'],
            {'statFlat': {'endurance': 3}, 'stamina': 1.01},
        )
        self.assertEqual(
            regulation['talisman_calculation_contract']['regulation_version'],
            '2.2.9.5',
        )
        self.assertEqual(
            regulation['binding_rune_calculation_contract']['runes'][
                'Leonine Stamina'
            ]['multipliers_by_copies'][2],
            1.0160000324249268,
        )
        self.assertEqual(
            regulation['fortune_calculation_contract']['main_fortunes'][
                'Spellsword'
            ]['statFlat']['mind'],
            6,
        )
        self.assertEqual(
            regulation['fortune_calculation_contract']['minor_fortune'][
                'stamina'
            ],
            1.01,
        )
        stamina = regulation['derived_curves']['endurance_stamina'][35]
        stamina *= viridian['modifiers']['stamina']
        stamina *= regulation['binding_rune_calculation_contract']['runes'][
            'Leonine Stamina'
        ]['multipliers_by_copies'][2]
        stamina *= enkindling['affixes']['Smoldering']['1']['stamina']
        stamina *= regulation['fortune_calculation_contract'][
            'minor_fortune'
        ]['stamina']
        self.assertEqual(math.floor(stamina), 1374)
        self.assertEqual(
            hashlib.sha256(response.content).hexdigest(), metadata['sha256']
        )

    def test_vanilla_calculation_bundle_contains_regulation_inputs(self):
        manifest_request = self.factory.get('/api/soulslike/data/manifest/')
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            manifest_response = api_sl_data_manifest(manifest_request)
        manifest = json.loads(manifest_response.content)
        metadata = manifest['datasets']['vanilla_calculations']

        request = self.factory.get(metadata['url'])
        response = api_sl_data_download(
            request, 'vanilla_calculations', metadata['revision']
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['calculation_contract_version'], 1)
        self.assertEqual(
            payload['regulation_sha256'],
            '7b6d07c357b639c902d48403ffe3612db35e0cf8d6fcc82d3fb24ea6eb6cf30a',
        )
        regulation = payload['payload']
        self.assertEqual(len(regulation['weapons']), 480)
        self.assertEqual(
            sum(len(value) for value in regulation['weapons'].values()),
            3216,
        )
        self.assertEqual(
            regulation['derived_curves']['vigor_hp'][10], 414
        )
        self.assertEqual(
            regulation['talismans']['Viridian Amber Medallion'][
                'modifiers'
            ],
            {'stamina': 1.11},
        )
        self.assertEqual(
            regulation['talismans']['Ritual Sword Talisman']['modifiers'],
            {},
        )
        self.assertEqual(
            regulation['talismans']['Blue Dancer Charm']['modifiers'],
            {'physicalEquipScaling': 'vanilla_blue_dancer'},
        )
        self.assertEqual(
            regulation['crystal_tears']['Winged Crystal Tear']['modifiers'],
            {'eqload': 4.5},
        )
        self.assertEqual(
            regulation['calculation_scope'],
            'deterministic_build_state_only',
        )
        self.assertEqual(
            hashlib.sha256(response.content).hexdigest(), metadata['sha256']
        )

    def test_stale_revision_is_rejected(self):
        request = self.factory.get('/api/soulslike/data/bosses_err/stale/')
        with patch(
            'app.questlog_web.views_soulslike_data.get_db_session',
            side_effect=_fake_session,
        ):
            response = api_sl_data_download(
                request, 'bosses_err', 'stale'
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn('manifest_url', json.loads(response.content))
        self.assertEqual(response['Access-Control-Allow-Origin'], '*')
        self.assertEqual(response['Cache-Control'], 'no-store')
