from django.test import SimpleTestCase

from app.questlog_web.soulslike_boss_catalog import (
    find_supplemental_boss,
    supplemental_bosses,
)


class SupplementalBossCatalogTests(SimpleTestCase):
    def test_err_catalog_contains_caelid_alabaster_lord(self):
        bosses = supplemental_bosses('elden_ring', 'err')

        self.assertIn({
            'key': 'Alabaster Lord (East of the Church of the Plague)',
            'name': 'Alabaster Lord',
            'location': 'East of the Church of the Plague',
            'region': 'Caelid',
            'tier': 'great_enemy',
        }, bosses)

    def test_err_catalog_keeps_war_dead_leonine_separate(self):
        bosses = supplemental_bosses('elden_ring', 'err')

        self.assertIn({
            'key': 'Leonine Misbegotten (War-Dead Catacombs)',
            'name': 'Leonine Misbegotten',
            'location': 'War-Dead Catacombs',
            'region': 'Caelid',
            'tier': 'great_enemy',
        }, bosses)
        self.assertNotIn(
            'Leonine Misbegotten (Castle Morne)',
            {boss['key'] for boss in bosses},
        )

    def test_legacy_err_game_name_is_normalized(self):
        boss = find_supplemental_boss(
            'err',
            'vanilla',
            'Alabaster Lord (East of the Church of the Plague)',
        )

        self.assertIsNotNone(boss)
        self.assertEqual(boss['region'], 'Caelid')

    def test_vanilla_catalog_is_unchanged(self):
        self.assertEqual(supplemental_bosses('elden_ring', 'vanilla'), [])

    def test_callers_cannot_mutate_the_shared_catalog(self):
        bosses = supplemental_bosses('elden_ring', 'err')
        bosses[0]['name'] = 'Changed'

        fresh = supplemental_bosses('elden_ring', 'err')
        self.assertEqual(fresh[0]['name'], 'Alabaster Lord')
