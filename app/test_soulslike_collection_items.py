from pathlib import Path

from django.test import SimpleTestCase

from app.questlog_web.views_pages import (
    _build_collection_items_from_payload,
    _sync_linked_run_collection_items,
    _sync_linked_run_talismans,
)
from app.questlog_web.views_soulslike import _merge_linked_err_fortunes


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _BuildDb:
    def __init__(self, row):
        self.row = row
        self.params = None

    def execute(self, statement, params):
        self.params = params
        return _Result(self.row)


class _RowsResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows


class _TalismanSyncDb:
    def __init__(self):
        self.statements = []

    def execute(self, statement, params):
        sql = str(statement)
        self.statements.append((sql, params))
        if 'SELECT id, name FROM sl_talismans' in sql:
            return _RowsResult([(2, 'New Talisman'), (3, 'Kept Talisman')])
        if 'SELECT id FROM sl_collection_sessions' in sql:
            return _RowsResult([(10,)])
        if 'SELECT id, item_type, item_id, item_name, is_collected' in sql:
            return _RowsResult([
                (100, 'talisman', 1, 'Historical Talisman', 1),
                (101, 'talisman', 3, 'Kept Talisman', 1),
            ])
        return _RowsResult()


class SoulslikeCollectionItemTests(SimpleTestCase):
    def test_overlays_show_new_pickups_for_eight_seconds_then_remove_them(self):
        template_dir = (
            Path(__file__).parent
            / 'questlog_web/templates/questlog_web'
        )
        for template_name, render_function in (
            ('sl_overlay_collection.html', 'renderItems'),
            ('sl_overlay_combined.html', 'renderOverlayItems'),
        ):
            source = (template_dir / template_name).read_text(encoding='utf-8')
            with self.subTest(template=template_name):
                self.assertIn('var ITEM_FADE_MS = 8000;', source)
                self.assertIn('previous === false', source)
                self.assertIn("'|confirming:' + fading.map(", source)
                self.assertIn(
                    f'{render_function}(',
                    source,
                )
                self.assertIn('ITEM_FADE_MS + 50', source)

    def test_run_tracker_labels_binding_runes(self):
        source = (
            Path(__file__).parent
            / 'questlog_web/templates/questlog_web/sl_run_detail.html'
        ).read_text(encoding='utf-8')
        self.assertIn("binding_rune:  'Binding Rune'", source)
        self.assertIn('.type-binding_rune', source)

    def test_build_payload_derives_every_supported_collection_category(self):
        class CatalogDb:
            def execute(self, statement, params):
                sql = str(statement)
                if 'FROM sl_weapons' in sql:
                    return _RowsResult([(1, 'Test Sword', 'Built-in Skill')])
                if 'FROM sl_armor' in sql:
                    return _RowsResult([(2, 'Test Helm')])
                if 'FROM sl_talismans' in sql:
                    return _RowsResult([(3, 'Test Talisman')])
                if 'FROM sl_err_spells' in sql:
                    return _RowsResult([(5, 'ERR Spell')])
                if 'FROM sl_spells' in sql:
                    return _RowsResult([(4, 'ER Spell')])
                return _RowsResult()

        items = _build_collection_items_from_payload(CatalogDb(), {
            'rh1_weapon_id': 1,
            'rh1_aow_name': 'Custom Ash',
            'helm_id': 2,
            'talisman_1_id': 3,
            'spells': [4, 10005],
            'spirit_ash_name': 'Test Spirit',
            'tear_1_name': 'First Tear',
            'tear_2_name': 'Second Tear',
            'fortune_name': 'Test Fortune',
            'minor_fortune_name': 'Test Minor Fortune',
            'curio_selections': {'Test Curio': {'active': True}},
            'rune_inventory': [{'name': 'Test Rune', 'copies': 2}],
        }, 'err')

        item_types = [item['item_type'] for item in items]
        self.assertEqual(set(item_types), {
            'weapon', 'aow', 'armor', 'talisman', 'spell', 'spirit_ash',
            'crystal_tear', 'fortune', 'minor_fortune', 'curio',
            'binding_rune',
        })
        self.assertEqual(item_types.count('spell'), 2)
        self.assertEqual(item_types.count('crystal_tear'), 2)

    def test_linked_err_build_adds_main_and_minor_fortunes(self):
        db = _BuildDb(('Sentinel', 'Brave'))
        items = _merge_linked_err_fortunes(
            db, [], build_id=12, user_id=4, game_mode='err'
        )

        self.assertEqual(db.params, {'bid': 12, 'uid': 4})
        self.assertEqual(items, [
            {
                'item_type': 'fortune',
                'item_id': None,
                'item_name': 'Sentinel',
                'location_hint': 'Main Fortune',
            },
            {
                'item_type': 'minor_fortune',
                'item_id': None,
                'item_name': 'Brave',
                'location_hint': 'Minor Fortune',
            },
        ])

    def test_new_client_minor_fortune_is_not_duplicated(self):
        db = _BuildDb(('Sentinel', 'Brave'))
        supplied = [
            {'item_type': 'fortune', 'item_name': 'Sentinel'},
            {'item_type': 'minor_fortune', 'item_name': 'Brave'},
        ]
        items = _merge_linked_err_fortunes(
            db, supplied, build_id=12, user_id=4, game_mode='err'
        )

        self.assertEqual(items, supplied)

    def test_unsaved_client_selection_wins_over_linked_build(self):
        db = _BuildDb(('Sentinel', 'Brave'))
        supplied = [
            {'item_type': 'fortune', 'item_name': 'Barbarian'},
            {'item_type': 'minor_fortune', 'item_name': 'Reeds'},
        ]
        items = _merge_linked_err_fortunes(
            db, supplied, build_id=12, user_id=4, game_mode='err'
        )

        self.assertEqual(items, supplied)

    def test_build_update_syncs_talismans_and_preserves_existing_status(self):
        db = _TalismanSyncDb()

        summary = _sync_linked_run_talismans(
            db,
            build_id=12,
            user_id=4,
            game='err',
            build_name='Test Build',
            talisman_ids=[2, 3, None, None],
        )

        self.assertEqual(summary, {
            'runs': 1, 'added': 1, 'removed': 0,
            'updated': 1, 'preserved': 1,
        })
        statements = '\n'.join(sql for sql, _ in db.statements)
        self.assertIn('INSERT INTO sl_collection_item_status', statements)
        self.assertNotIn('DELETE FROM sl_collection_item_status', statements)
        preserve_update = next(
            (sql, params) for sql, params in db.statements
            if sql.lstrip().startswith('UPDATE sl_collection_item_status')
        )
        self.assertIn('is_collected=CASE WHEN :was_collected=1', preserve_update[0])
        self.assertEqual(preserve_update[1]['row_id'], 101)
        inserted = next(
            params for sql, params in db.statements
            if sql.lstrip().startswith('INSERT INTO sl_collection_item_status')
        )
        self.assertEqual(inserted['item_id'], 2)
        self.assertEqual(inserted['collected'], 0)

    def test_explicit_app_inventory_updates_collected_state(self):
        db = _TalismanSyncDb()

        _sync_linked_run_talismans(
            db,
            build_id=12,
            user_id=4,
            game='err',
            build_name='Test Build',
            talisman_ids=[2, 3],
            collected_talisman_ids=[2],
        )

        collected_updates = [
            params for sql, params in db.statements
            if sql.lstrip().startswith('UPDATE sl_collection_item_status')
            and 'is_collected=CASE' in sql
        ]
        self.assertEqual(len(collected_updates), 1)
        self.assertEqual(collected_updates[0]['row_id'], 101)
        # An existing collected item remains collected even when it is absent
        # from the app's current inventory list.
        self.assertEqual(collected_updates[0]['collected'], 0)
        inserted = next(
            params for sql, params in db.statements
            if sql.lstrip().startswith('INSERT INTO sl_collection_item_status')
        )
        self.assertEqual(inserted['item_id'], 2)
        self.assertEqual(inserted['collected'], 1)

    def test_all_build_item_types_are_additive_and_never_delete_history(self):
        db = _TalismanSyncDb()
        desired = [
            {'item_type': 'weapon', 'item_id': 9, 'item_name': 'New Sword'},
            {'item_type': 'crystal_tear', 'item_name': 'New Tear'},
            {'item_type': 'spirit_ash', 'item_name': 'New Ash'},
            {'item_type': 'binding_rune', 'item_name': 'New Rune'},
        ]

        summary = _sync_linked_run_collection_items(
            db, build_id=12, user_id=4, game='err',
            build_name='Test Build', desired=desired,
        )

        self.assertEqual(summary['added'], 4)
        self.assertEqual(summary['removed'], 0)
        statements = '\n'.join(sql for sql, _ in db.statements)
        self.assertNotIn('DELETE FROM sl_collection_item_status', statements)
        inserted_types = {
            params['item_type'] for sql, params in db.statements
            if sql.lstrip().startswith('INSERT INTO sl_collection_item_status')
        }
        self.assertEqual(inserted_types, {
            'weapon', 'crystal_tear', 'spirit_ash', 'binding_rune',
        })

    def test_sealing_curio_does_not_remove_collected_curio_history(self):
        class CurioDb:
            def __init__(self):
                self.statements = []

            def execute(self, statement, params):
                sql = str(statement)
                self.statements.append((sql, params))
                if 'SELECT id FROM sl_collection_sessions' in sql:
                    return _RowsResult([(10,)])
                if 'SELECT id, item_type, item_id, item_name, is_collected' in sql:
                    return _RowsResult([
                        (200, 'curio', 0, 'Academy Curio', 1),
                    ])
                return _RowsResult()

        db = CurioDb()
        summary = _sync_linked_run_collection_items(
            db, build_id=12, user_id=4, game='err',
            build_name='Test Build', desired=[],
        )

        self.assertEqual(summary['removed'], 0)
        statements = '\n'.join(sql for sql, _ in db.statements)
        self.assertNotIn('DELETE FROM sl_collection_item_status', statements)
        self.assertNotIn('is_collected=0', statements)

    def test_vanilla_run_does_not_query_err_build(self):
        db = _BuildDb(('Sentinel', 'Brave'))
        supplied = [{'item_type': 'weapon', 'item_name': 'Claymore'}]
        items = _merge_linked_err_fortunes(
            db, supplied, build_id=12, user_id=4, game_mode='vanilla'
        )

        self.assertEqual(items, supplied)
        self.assertIsNone(db.params)
