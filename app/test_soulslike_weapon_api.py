import json
from contextlib import contextmanager
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from app.questlog_web.views_pages import (
    api_sl_ar_data,
    api_sl_armor,
    api_sl_classes,
    api_sl_crystal_tears,
    api_sl_derived_curves,
    api_sl_talismans,
    api_sl_weapon_ar_variants,
    api_sl_weapons,
    _effective_err_reinforce_type,
    _current_err_armor,
    _current_vanilla_talisman,
    _err_weapon_affinities,
    _build_enkindling_save_data,
    _sanitize_enkindling,
    _ENKINDLE_SET_CLAUSE,
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    def execute(self, statement, params):
        sql = str(statement)
        if 'SELECT DISTINCT weapon_type' in sql:
            return _Rows([('Dagger',)])
        self.weapon_sql = sql
        return _Rows([
            (
                484, 'Reduvia', 'Dagger',
                79, 0, 0, 0, 0, 110, 2.5,
                'E', 'D', '-', '-', 'D',
                5, 13, 0, 0, 13,
                0, 'Reduvia Blood Blade', '',
                1, 1, 'Blood', None,
            ),
            (
                26, 'Ruins Greatsword', 'Colossal Sword',
                124, 37, 0, 0, 0, 100, 23.0,
                'B', 'E', 'D', '-', '-',
                50, 0, 16, 0, 0,
                0, 'Wave of Destruction', '',
                1, 1, None,
                'Added the Gravitational affinity effect. Converted Magic damage portion into Lightning.',
            ),
        ])


class SoulslikeWeaponApiTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_err_weapon_exposes_fixed_skill_affinity(self):
        fake_db = _FakeDb()

        @contextmanager
        def fake_session():
            yield fake_db

        request = self.factory.get('/api/soulslike/weapons/', {
            'game': 'err',
            'limit': '1000',
        })
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_weapons(request)

        payload = json.loads(response.content)
        self.assertEqual(payload['weapons'][0]['affinity'], 'Blood')
        self.assertEqual(payload['weapons'][0]['affinities'], ['Blood'])
        self.assertEqual(payload['weapons'][1]['affinity'], 'Gravitational')
        self.assertEqual(payload['weapons'][1]['affinities'], ['Gravitational'])
        self.assertIn('sl_err_aow_skills', fake_db.weapon_sql)
        self.assertIn('a.affinity', fake_db.weapon_sql)
        self.assertIn('sl_err_vanilla_weapon_changes', fake_db.weapon_sql)
        ruins = payload['weapons'][1]
        self.assertEqual(ruins['damage'], {'phy': 93, 'mag': 0, 'fir': 0, 'lit': 59, 'hol': 0})
        self.assertEqual(ruins['requirements'], {'str': 50, 'dex': 5, 'int': 25, 'fai': 0, 'arc': 0})
        self.assertEqual(ruins['weight'], 15.5)
        self.assertTrue(ruins['is_somber'])

    def test_multi_affinity_weapon_preserves_every_value(self):
        self.assertEqual(
            _err_weapon_affinities(
                'Added the Lightning and Gravitational affinity effects.'
            ),
            ['Lightning', 'Gravitational'],
        )

    def test_skill_affinity_is_a_fallback_without_duplicates(self):
        self.assertEqual(_err_weapon_affinities('', 'Blood'), ['Blood'])
        self.assertEqual(
            _err_weapon_affinities('Added the Cold affinity effect.', 'Cold'),
            ['Cold'],
        )

    def test_err_reinforce_profiles_are_normalized_without_db_changes(self):
        self.assertEqual(
            _effective_err_reinforce_type('Gravitational', 11600), 12000
        )
        self.assertEqual(
            _effective_err_reinforce_type('Soporific', 10000), 11400
        )
        self.assertEqual(
            _effective_err_reinforce_type('Fated', 11400, 10200), 10200
        )
        self.assertEqual(
            _effective_err_reinforce_type('Standard', 19000), 19000
        )

    def test_err_ar_api_uses_weapon_specific_fated_profile(self):
        rows = [
            ('Soporific', 0, '{}', '{}', '{}', 101400, '{}', 10200),
            ('Fated', 0, '{}', '{}', '{}', 19190, '{}', 11400),
            ('Gravitational', 0, '{}', '{}', '{}', 102000, '{}', 11600),
        ]

        @contextmanager
        def fake_session():
            yield _FakeDbForRows(rows)

        request = self.factory.get('/api/soulslike/weapons/Test/ar-variants/', {
            'game': 'err',
        })
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_weapon_ar_variants(request, 'Test')

        variants = {
            row['affinity']: row['reinforce_type_id']
            for row in json.loads(response.content)['variants']
        }
        self.assertEqual(variants['Soporific'], 11400)
        self.assertEqual(variants['Fated'], 10200)
        self.assertEqual(variants['Gravitational'], 12000)

    def test_vanilla_ar_api_preserves_stored_profile(self):
        rows = [
            ('Gravitational', 0, '{}', '{}', '{}', 102000, '{}', 11600),
        ]

        @contextmanager
        def fake_session():
            yield _FakeDbForRows(rows)

        request = self.factory.get('/api/soulslike/weapons/Test/ar-variants/', {
            'game': 'elden_ring',
        })
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_weapon_ar_variants(request, 'Test')

        variant = json.loads(response.content)['variants'][0]
        self.assertEqual(variant['reinforce_type_id'], 11600)

    def test_vanilla_sheet_modifiers_exclude_conditional_talismans(self):
        self.assertEqual(
            _current_vanilla_talisman('Ritual Sword Talisman')['modifiers'],
            {},
        )
        self.assertEqual(
            _current_vanilla_talisman('Claw Talisman')['modifiers'],
            {},
        )

    def test_vanilla_deterministic_talisman_scaling_is_preserved(self):
        self.assertEqual(
            _current_vanilla_talisman('Magic Scorpion Charm')['modifiers'],
            {
                'attackPve': {'1': 1.12},
                'attackPvp': {'1': 1.08},
            },
        )
        self.assertEqual(
            _current_vanilla_talisman('Blue Dancer Charm')['modifiers'],
            {'physicalEquipScaling': 'vanilla_blue_dancer'},
        )
        self.assertAlmostEqual(
            _current_vanilla_talisman("Bull-Goat's Talisman")[
                'modifiers'
            ]['poiseMult'],
            4 / 3,
        )

    def test_vanilla_crystal_tears_expose_regulation_sheet_modifiers(self):
        @contextmanager
        def fake_session():
            yield object()

        request = self.factory.get(
            '/api/soulslike/crystal-tears/',
            {'game': 'elden_ring'},
        )
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_crystal_tears(request)

        payload = json.loads(response.content)
        tears = {tear['name']: tear for tear in payload['tears']}
        self.assertEqual(
            tears['Strength-knot Crystal Tear']['modifiers'],
            {'statFlat': {'strength': 10}},
        )
        self.assertEqual(
            tears['Winged Crystal Tear']['modifiers'],
            {'eqload': 4.5},
        )
        self.assertEqual(
            tears['Magic-Shrouding Cracked Tear']['modifiers'],
            {
                'attackPve': {'1': 1.20},
                'attackPvp': {'1': 1.125},
            },
        )

    def test_err_ar_data_uses_current_regulation_export(self):
        request = self.factory.get('/api/soulslike/ar-data/', {'game': 'err'})
        response = api_sl_ar_data(request)

        payload = json.loads(response.content)
        reinforce = payload['reinforce']
        self.assertEqual(payload['regulation_version'], '2.2.9.5')
        self.assertEqual(
            reinforce['12000']['scaling'],
            {'str': 0.6, 'dex': 0.55, 'int': 0.85, 'fai': 0.85, 'arc': 1.0},
        )
        self.assertEqual(reinforce['12000']['max_level'], 25)
        self.assertEqual(len(reinforce['12000']['levels']), 26)
        self.assertEqual(reinforce['19000']['max_level'], 10)
        self.assertEqual(len(reinforce['19000']['levels']), 11)

    def test_err_weapon_variants_use_current_regulation_values(self):
        request = self.factory.get('/api/soulslike/weapons/Ruins/ar-variants/', {
            'game': 'err',
        })
        response = api_sl_weapon_ar_variants(request, 'Ruins Greatsword')
        payload = json.loads(response.content)
        variant = payload['variants'][0]
        self.assertEqual(payload['regulation_version'], '2.2.9.5')
        self.assertEqual(variant['attack'], {'0': 93, '3': 59})
        self.assertEqual(variant['requirements'], {'str': 50, 'dex': 5, 'int': 25})
        self.assertEqual(variant['max_upgrade'], 10)
        self.assertEqual(variant['weight'], 15.5)

    def test_err_affinity_variants_expose_exact_regulation_weight(self):
        request = self.factory.get('/api/soulslike/weapons/Zwei/ar-variants/', {
            'game': 'err',
        })
        response = api_sl_weapon_ar_variants(request, 'Zweihänder')
        variants = {
            row['affinity']: row
            for row in json.loads(response.content)['variants']
        }
        self.assertEqual(variants['Standard']['weight'], 14.5)
        self.assertEqual(variants['Gravitational']['weight'], 7.25)

    def test_err_fated_weight_remains_weapon_specific(self):
        request = self.factory.get('/api/soulslike/weapons/Estoc/ar-variants/', {
            'game': 'err',
        })
        response = api_sl_weapon_ar_variants(request, 'Estoc')
        variants = {
            row['affinity']: row
            for row in json.loads(response.content)['variants']
        }
        self.assertEqual(variants['Standard']['weight'], 4.5)
        self.assertEqual(variants['Fated']['weight'], 2.2)

    def test_omitted_enkindling_fields_preserve_existing_build_values(self):
        result = _build_enkindling_save_data({}, 'err', db=object())
        self.assertEqual(result['rh1_enk_provided'], 0)
        self.assertIn(
            'CASE WHEN :rh1_enk_provided=1',
            _ENKINDLE_SET_CLAUSE,
        )

    def test_explicit_empty_enkindling_fields_clear_saved_value(self):
        result = _build_enkindling_save_data({
            'rh1_enkindle_affix': None,
            'rh1_enkindle_rarity': None,
        }, 'err', db=object())
        self.assertEqual(result['rh1_enk_provided'], 1)
        self.assertIsNone(result['rh1_enk_affix'])
        self.assertIsNone(result['rh1_enk_rarity'])

    def test_nested_app_enkindling_payload_is_supported(self):
        class _OneRow:
            def fetchone(self):
                return (1,)

        class _EnkindleDb:
            def execute(self, statement, params=None):
                return _OneRow()

        result = _build_enkindling_save_data({
            'weapons': {'rh1_aow': 'Flame of the Redmanes'},
            'enkindling': {
                'rh1': {'affix': 'Mundane', 'rarity': '2-star'},
            },
        }, 'err', db=_EnkindleDb())
        self.assertEqual(result['rh1_enk_provided'], 1)
        self.assertEqual(result['rh1_enk_affix'], 'Mundane')
        self.assertEqual(result['rh1_enk_rarity'], 'rare')

    def test_mundane_matches_eligible_endpoint_universal_fallback(self):
        class _OneRow:
            def fetchone(self):
                return ('Mundane',)

        class _EnkindleDb:
            def execute(self, statement, params=None):
                return _OneRow()

        self.assertEqual(
            _sanitize_enkindling(
                'Unseeded Built-in Skill', 'Mundane', 'common', db=_EnkindleDb()
            ),
            ('Mundane', 'common'),
        )

    def test_err_armor_export_uses_current_regulation_values(self):
        self.assertEqual(
            _current_err_armor("Radahn's Redmane Helm"),
            {
                'regulation_id': 470000,
                'type': 'helm',
                'weight': 13.1,
                'poise': 11.0,
            },
        )

    def test_err_armor_api_keeps_catalog_id_and_overlays_regulation(self):
        class FakeArmorDb:
            def __init__(self):
                self.params = None

            def execute(self, statement, params):
                self.params = params
                return _Rows([(
                    42, "Radahn's Redmane Helm", 'helm',
                    6.8, 4.8, 5.0, 4.5, 4.8, 9, 7.5, '',
                )])

        fake_db = FakeArmorDb()

        @contextmanager
        def fake_session():
            yield fake_db

        request = self.factory.get('/api/soulslike/armor/', {
            'game': 'err',
            'limit': '1000',
        })
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_armor(request)

        payload = json.loads(response.content)
        armor = payload['armor'][0]
        self.assertEqual(fake_db.params['g'], 'elden_ring')
        self.assertEqual(armor['id'], 42)
        self.assertEqual(armor['weight'], 13.1)
        self.assertEqual(armor['poise'], 11.0)
        self.assertEqual(payload['regulation_version'], '2.2.9.5')

    def test_err_talisman_api_exposes_regulation_equip_load(self):
        rows = [(7, 'Arsenal Charm', 'effect', 0.8, '')]

        @contextmanager
        def fake_session():
            yield _FakeDbForRows(rows)

        request = self.factory.get('/api/soulslike/talismans/', {
            'game': 'err',
            'limit': '1000',
        })
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_talismans(request)

        payload = json.loads(response.content)
        talisman = payload['talismans'][0]
        self.assertEqual(talisman['id'], 7)
        self.assertEqual(talisman['weight'], 0.0)
        self.assertEqual(talisman['equip_load_mult'], 1.06)
        self.assertEqual(payload['regulation_version'], '2.2.9.5')

    def test_err_talisman_api_exposes_deterministic_stat_modifiers(self):
        rows = [(7, 'Viridian Amber Medallion', 'effect', 9.9, '')]

        @contextmanager
        def fake_session():
            yield _FakeDbForRows(rows)

        request = self.factory.get('/api/soulslike/talismans/', {
            'game': 'err',
            'limit': '1000',
        })
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_talismans(request)

        talisman = json.loads(response.content)['talismans'][0]
        self.assertEqual(
            talisman['modifiers'],
            {'statFlat': {'endurance': 3}, 'stamina': 1.01},
        )

    def test_err_catalyst_exposes_spell_scaling_flag(self):
        request = self.factory.get('/api/soulslike/weapons/Meteorite/ar-variants/', {
            'game': 'err',
        })
        response = api_sl_weapon_ar_variants(request, 'Meteorite Staff')
        variant = json.loads(response.content)['variants'][0]
        self.assertTrue(variant['sorcery_tool'])
        self.assertFalse(variant['incantation_tool'])
        self.assertEqual(variant['calc_correct_graph_ids']['1'], 30)

    def test_err_derived_stats_use_current_regulation_export(self):
        request = self.factory.get('/api/soulslike/derived-curves/', {
            'game': 'err',
        })
        response = api_sl_derived_curves(request)
        payload = json.loads(response.content)
        self.assertEqual(payload['regulation_version'], '2.2.9.5')
        self.assertEqual(payload['curves']['vigor_hp'][1], 314)
        self.assertEqual(payload['curves']['vigor_hp'][99], 4800)
        self.assertEqual(payload['curves']['mind_fp'][99], 3400)
        self.assertEqual(payload['curves']['endurance_stamina'][99], 2000)
        self.assertEqual(payload['weight_sources']['fortunes']['Sentinel'], 1.04)
        self.assertEqual(payload['weight_sources']['fortunes']['Dynasts'], 0.86)
        self.assertEqual(
            payload['weight_sources']['crystal_tears']['Winged Crystal Tear'],
            1.1,
        )

    def test_err_classes_keep_db_ids_but_use_current_regulation_stats(self):
        rows = [(77, 'Prisoner', 99, 1, 1, 1, 1, 1, 1, 1, 1)]

        @contextmanager
        def fake_session():
            yield _FakeDbForRows(rows)

        request = self.factory.get('/api/soulslike/classes/', {'game': 'err'})
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_classes(request)

        payload = json.loads(response.content)
        prisoner = payload['classes'][0]
        self.assertEqual(prisoner['id'], 77)
        self.assertEqual(prisoner['level'], 10)
        self.assertEqual(
            [prisoner[key] for key in (
                'vigor', 'mind', 'endurance', 'strength', 'dexterity',
                'intelligence', 'faith', 'arcane',
            )],
            [12, 13, 11, 10, 14, 14, 6, 9],
        )

    def test_vanilla_ar_data_does_not_use_err_scaling_override(self):
        request = self.factory.get('/api/soulslike/ar-data/', {
            'game': 'elden_ring',
        })
        response = api_sl_ar_data(request)

        payload = json.loads(response.content)
        reinforce = payload['reinforce']
        self.assertEqual(
            payload['regulation_sha256'],
            '7b6d07c357b639c902d48403ffe3612db35e0cf8d6fcc82d3fb24ea6eb6cf30a',
        )
        self.assertEqual(reinforce['0']['max_level'], 25)
        self.assertEqual(len(reinforce['0']['levels']), 26)
        self.assertAlmostEqual(
            reinforce['0']['levels'][1]['attack']['0'],
            1.0579999685287476,
        )
        self.assertNotEqual(
            reinforce.get('12000', {}).get('scaling'),
            {'str': 9},
        )

    def test_vanilla_weapon_variants_use_verified_regulation_values(self):
        request = self.factory.get(
            '/api/soulslike/weapons/Dagger/ar-variants/',
            {'game': 'elden_ring'},
        )
        response = api_sl_weapon_ar_variants(request, 'Dagger')
        payload = json.loads(response.content)
        variants = {
            value['affinity']: value for value in payload['variants']
        }

        self.assertEqual(variants['Standard']['attack'], {'0': 74})
        self.assertEqual(
            variants['Standard']['requirements'],
            {'str': 5, 'dex': 9},
        )
        self.assertEqual(variants['Standard']['weight'], 1.5)
        self.assertEqual(variants['Standard']['max_upgrade'], 25)
        self.assertEqual(variants['Heavy']['reinforce_type_id'], 100)

    def test_vanilla_weapon_lookup_normalizes_catalog_accents(self):
        request = self.factory.get(
            '/api/soulslike/weapons/Zwei/ar-variants/',
            {'game': 'elden_ring'},
        )
        response = api_sl_weapon_ar_variants(request, 'Zweihänder')
        payload = json.loads(response.content)

        self.assertGreater(len(payload['variants']), 1)
        self.assertEqual(payload['variants'][0]['weight'], 15.5)

    def test_vanilla_derived_stats_use_exact_regulation_curves(self):
        request = self.factory.get(
            '/api/soulslike/derived-curves/',
            {'game': 'elden_ring'},
        )
        response = api_sl_derived_curves(request)
        curves = json.loads(response.content)['curves']

        self.assertEqual(curves['vigor_hp'][10], 414)
        self.assertEqual(curves['mind_fp'][10], 78)
        self.assertEqual(curves['endurance_stamina'][10], 96)
        self.assertEqual(curves['endurance_equip_load'][8], 45.0)
        self.assertEqual(curves['endurance_equip_load'][10], 48.2)

    def test_vanilla_talisman_api_exposes_regulation_modifiers(self):
        rows = [(7, 'Viridian Amber Medallion', 'effect', 9.9, '')]

        @contextmanager
        def fake_session():
            yield _FakeDbForRows(rows)

        request = self.factory.get('/api/soulslike/talismans/', {
            'game': 'elden_ring',
            'limit': '1000',
        })
        with patch(
            'app.questlog_web.views_pages.get_db_session',
            side_effect=fake_session,
        ):
            response = api_sl_talismans(request)

        talisman = json.loads(response.content)['talismans'][0]
        self.assertEqual(talisman['weight'], 0.30000001192092896)
        self.assertEqual(talisman['modifiers'], {'stamina': 1.11})


class _FakeDbForRows:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params):
        return _Rows(self.rows)
