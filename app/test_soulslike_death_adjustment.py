import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve

from app.questlog_web.views_soulslike import (
    HOLLOW_STREAK_DB_MAX,
    _fury_after_death,
    _fury_after_recovery,
    api_sl_set_deaths,
    api_sl_set_session_deaths,
    api_sl_subtract_death,
    _rage_from_event_history,
)


RUN_TEMPLATE = (
    Path(__file__).parent
    / 'questlog_web/templates/questlog_web/sl_run_detail.html'
)
VIEW_SOURCE = Path(__file__).parent / 'questlog_web/views_soulslike.py'
COMBINED_OVERLAY = (
    Path(__file__).parent
    / 'questlog_web/templates/questlog_web/sl_overlay_combined.html'
)
COLLECTION_OVERLAY = (
    Path(__file__).parent
    / 'questlog_web/templates/questlog_web/sl_overlay_collection.html'
)
APP_HANDOFF = Path(__file__).parent / 'docs/eldentracker_api_handoff.md'
HOLLOW_UPGRADE_COMMAND = (
    Path(__file__).parent
    / 'management/commands/upgrade_soulslike_hollow_counters.py'
)


class _Result:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._row


class _CorrectionDb:
    def __init__(self):
        self.updated = None
        self.committed = False

    def execute(self, statement, params):
        sql = str(statement)
        if 'FROM sl_collection_sessions' in sql and 'FOR UPDATE' in sql:
            return _Result(row=(
                10, 7, 1423, 901, 0,
                100, 'HOLLOW', 127, 1000, 0, 0,
            ))
        if sql.lstrip().startswith('DELETE FROM sl_death_events'):
            return _Result(rowcount=901)
        if 'SELECT died_at FROM sl_death_events' in sql:
            return _Result(rows=[(1,), (2,), (3,)])
        if 'SELECT defeated_at, tier FROM sl_session_bosses' in sql:
            return _Result(rows=[])
        if sql.lstrip().startswith('UPDATE sl_collection_sessions'):
            self.updated = params
            return _Result(rowcount=1)
        raise AssertionError(f'Unexpected SQL: {sql}')

    def commit(self):
        self.committed = True


class _UndoDb:
    def __init__(self):
        self.updated = None
        self.deleted_event_id = None
        self.committed = False

    def execute(self, statement, params):
        sql = ' '.join(str(statement).split())
        if 'FROM sl_collection_sessions' in sql and 'FOR UPDATE' in sql:
            return _Result(row=(
                6, 968, 100, 132, 4,
                'Godskin Apostle',
                'Godskin Apostle (Dominula, Windmill Village)',
                533, 533, 370000, 'listener', 1000,
            ))
        if 'SET undo_count=undo_count+1' in sql:
            return _Result(rowcount=1)
        if 'SELECT id, boss_name, boss_key' in sql and 'FOR UPDATE' in sql:
            return _Result(row=(
                1787,
                'Godskin Apostle',
                'Godskin Apostle (Dominula, Windmill Village)',
            ))
        if sql.startswith('DELETE FROM sl_death_events'):
            self.deleted_event_id = params['event_id']
            return _Result(rowcount=1)
        if 'SELECT boss_name, boss_key' in sql and 'LIMIT 1' in sql:
            return _Result(row=(
                'Godskin Apostle',
                'Godskin Apostle (Dominula, Windmill Village)',
            ))
        if sql.startswith('UPDATE sl_collection_sessions SET death_count'):
            self.updated = params
            return _Result(rowcount=1)
        if 'COUNT(*) FROM sl_death_events' in sql and 'boss_name IS NOT NULL' in sql:
            return _Result(row=460)
        if 'COUNT(*) FROM sl_session_bosses' in sql:
            return _Result(row=23)
        if 'COUNT(*) FROM sl_death_events' in sql and 'boss_key=:boss_key' in sql:
            return _Result(row=3)
        raise AssertionError(f'Unexpected SQL: {sql}')

    def commit(self):
        self.committed = True


class _SessionCorrectionDb:
    def __init__(self):
        self.updated = None
        self.committed = False

    def execute(self, statement, params):
        sql = ' '.join(str(statement).split())
        if 'FROM sl_collection_sessions' in sql and 'FOR UPDATE' in sql:
            return _Result(row=(
                6, 7, 968, 4, 0,
                533, 533, 370000, 'listener', 1000,
            ))
        if sql.startswith('UPDATE sl_collection_sessions'):
            self.updated = params
            return _Result(rowcount=1)
        raise AssertionError(f'Unexpected SQL: {sql}')

    def commit(self):
        self.committed = True


@contextmanager
def _correction_session(db):
    yield db


class SoulslikeDeathAdjustmentTests(SimpleTestCase):
    def test_absolute_total_death_route_is_registered(self):
        match = resolve('/api/soulslike/session/test/set-total-deaths/')
        self.assertEqual(match.url_name, 'api_sl_set_total_deaths')

    def test_session_death_route_uses_distinct_session_handler(self):
        match = resolve('/api/soulslike/session/test/set-session-deaths/')
        self.assertEqual(match.url_name, 'api_sl_set_session_deaths')
        self.assertEqual(match.func.__name__, 'api_sl_set_session_deaths')

    def test_setting_901_repairs_prior_additive_901_without_adding_again(self):
        request = RequestFactory().post(
            '/api/soulslike/session/test/set-total-deaths/',
            data=json.dumps({'total_deaths': 901}),
            content_type='application/json',
        )
        request.session = {'web_user_id': 7}
        request.user = AnonymousUser()
        db = _CorrectionDb()
        with patch(
            'app.questlog_web.views_soulslike.get_db_session',
            side_effect=lambda: _correction_session(db),
        ), patch('app.questlog_web.views_soulslike.sse_publish'):
            response = api_sl_set_deaths(request, 'test')

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['deaths'], 901)
        self.assertEqual(payload['session_deaths'], 0)
        self.assertEqual(payload['cleaned_adjustments'], 901)
        self.assertEqual(db.updated['deaths'], 901)
        self.assertEqual(db.updated['session_deaths'], 0)
        self.assertTrue(db.committed)

    def test_undo_returns_recalculated_boss_and_death_metrics(self):
        request = RequestFactory().post(
            '/api/soulslike/session/test/subtract-death/',
            data=json.dumps({}),
            content_type='application/json',
        )
        request.resolver_match = resolve(
            '/api/soulslike/session/test/subtract-death/'
        )
        db = _UndoDb()
        with patch(
            'app.questlog_web.views_soulslike.get_db_session',
            side_effect=lambda: _correction_session(db),
        ), patch('app.questlog_web.views_soulslike.sse_publish') as publish:
            response = api_sl_subtract_death(request, 'test')

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['deaths'], 967)
        self.assertEqual(payload['session_deaths'], 3)
        self.assertEqual(payload['undone_event_id'], 1787)
        self.assertEqual(payload['undone_boss_deaths'], 3)
        self.assertEqual(payload['current_boss_deaths'], 3)
        self.assertEqual(payload['boss_deaths_total'], 460)
        self.assertEqual(payload['non_boss_deaths_total'], 507)
        self.assertEqual(payload['true_death_rate'], 20.0)
        self.assertEqual(payload['session_deaths_per_hour'], 20.3)
        self.assertEqual(payload['run_deaths_per_hour'], 9.4)
        self.assertEqual(payload['hollow_streak'], 131)
        self.assertEqual(db.deleted_event_id, 1787)
        self.assertEqual(db.updated['last_death_boss'], 'Godskin Apostle')
        self.assertTrue(db.committed)
        publish.assert_called_once()

    def test_session_correction_updates_session_without_changing_total(self):
        request = RequestFactory().post(
            '/api/soulslike/session/test/set-session-deaths/',
            data=json.dumps({'session_deaths': 2}),
            content_type='application/json',
        )
        request.session = {'web_user_id': 7}
        request.user = AnonymousUser()
        db = _SessionCorrectionDb()
        with patch(
            'app.questlog_web.views_soulslike.get_db_session',
            side_effect=lambda: _correction_session(db),
        ), patch('app.questlog_web.views_soulslike.sse_publish') as publish:
            response = api_sl_set_session_deaths(request, 'test')

        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['deaths'], 968)
        self.assertEqual(payload['total_deaths'], 968)
        self.assertEqual(payload['session_deaths'], 2)
        self.assertEqual(payload['session_deaths_per_hour'], 13.5)
        self.assertEqual(db.updated['session_deaths'], 2)
        self.assertTrue(db.committed)
        event = publish.call_args.args[1]
        self.assertEqual(event['event'], 'session_death_adjustment')

    def test_real_event_history_rebuilds_fury_without_synthetic_rows(self):
        state = _rage_from_event_history(
            death_times=[1, 2, 3, 4, 5],
            boss_events=[],
        )
        self.assertEqual(state['rage_pct'], 100)
        self.assertEqual(state['hollow_streak'], 1)
        self.assertEqual(state['hollow_entered_at'], 4)

    def test_boss_history_rebuild_closes_hollow_interval(self):
        state = _rage_from_event_history(
            death_times=[1, 2, 3, 4, 7, 8],
            boss_events=[(6, 'great_enemy')],
        )
        self.assertEqual(state['rage_pct'], 100)
        self.assertEqual(state['time_in_hollow_sec'], 2)
        self.assertEqual(state['hollow_entered_at'], 8)
        self.assertEqual(state['hollow_boss_kills'], 1)

    def test_hollow_stack_continues_past_old_signed_tinyint_limit(self):
        rage, streak = _fury_after_death(100, 127)
        self.assertEqual(rage, 100)
        self.assertEqual(streak, 128)
        self.assertGreater(HOLLOW_STREAK_DB_MAX, 127)

    def test_kill_recovery_consumes_hollow_stacks_before_visible_fury(self):
        self.assertEqual(
            _fury_after_recovery(100, 127, recovery_units=1),
            (100, 126),
        )
        self.assertEqual(
            _fury_after_recovery(100, 127, recovery_units=2),
            (100, 125),
        )
        self.assertEqual(
            _fury_after_recovery(100, 0, recovery_units=1),
            (75, 0),
        )
        self.assertEqual(
            _fury_after_recovery(100, 127, recovery_units=1, reset=True),
            (0, 0),
        )

    def test_event_history_rebuild_recovers_stacks_lost_to_old_cap(self):
        state = _rage_from_event_history(
            death_times=range(1, 133),
            boss_events=[],
        )
        self.assertEqual(state['rage_pct'], 100)
        self.assertEqual(state['hollow_streak'], 128)

    def test_schema_upgrade_preserves_rows_and_rebuilds_counters(self):
        command = HOLLOW_UPGRADE_COMMAND.read_text(encoding='utf-8')
        self.assertIn('BIGINT UNSIGNED NOT NULL DEFAULT 0', command)
        self.assertIn('_rage_from_event_history', command)
        self.assertNotIn('DELETE FROM', command.upper())

    def test_site_uses_authoritative_hollow_counter_after_undo_and_boss_kill(self):
        template = RUN_TEMPLATE.read_text(encoding='utf-8')
        self.assertIn(
            'updateRage(d.rage_pct,d.rage_name,d.is_hollow,d.hollow_streak)',
            template,
        )
        self.assertIn(
            'updateRage(d.rage_pct, d.rage_name, d.is_hollow, d.hollow_streak)',
            template,
        )
        self.assertNotIn(
            'updateRage(d.rage_pct, d.rage_name, d.is_hollow, 0)',
            template,
        )

    def test_overlay_refreshes_for_every_death_mutation_without_cache(self):
        overlay = COMBINED_OVERLAY.read_text(encoding='utf-8')
        view = VIEW_SOURCE.read_text(encoding='utf-8')
        self.assertIn("'total_death_adjustment'", overlay)
        self.assertIn("'session_death_adjustment'", overlay)
        self.assertIn("'undo'", overlay)
        self.assertIn("fetch(POLL_URL, {cache:'no-store'})", overlay)
        self.assertIn(
            "no-store, no-cache, must-revalidate, max-age=0", view
        )

    def test_editor_sets_absolute_total_without_creating_death_events(self):
        template = RUN_TEMPLATE.read_text(encoding='utf-8')
        view = VIEW_SOURCE.read_text(encoding='utf-8')

        self.assertIn("function editTotalDeaths()", template)
        self.assertIn("set-total-deaths/", template)
        self.assertIn("body:JSON.stringify({total_deaths:target})", template)
        self.assertNotIn("if (target === currentTotalDeaths) return", template)
        self.assertNotIn("INSERT INTO sl_death_events", view[view.index(
            'def api_sl_set_deaths'
        ):view.index('# ── Subtract death')])
        self.assertIn("'deaths': target", view)
        self.assertIn("area_name='__session_adjustment__'", view)

    def test_everything_else_reconciles_to_authoritative_total(self):
        view = VIEW_SOURCE.read_text(encoding='utf-8')
        self.assertIn(
            'non_boss_deaths = max(0, death_count - boss_deaths)', view
        )
        self.assertNotIn(
            'non_boss_deaths = max(0, total_death_events - boss_deaths)',
            view,
        )

    def test_death_response_returns_one_authoritative_breakdown(self):
        view = VIEW_SOURCE.read_text(encoding='utf-8')
        handoff = APP_HANDOFF.read_text(encoding='utf-8')
        self.assertIn('def _authoritative_death_breakdown(', view)
        self.assertIn("'death_breakdown_valid':", view)
        self.assertIn('**breakdown,', view)
        self.assertIn(
            'boss_deaths_total + non_boss_deaths_total == total_deaths',
            handoff,
        )
        self.assertIn(
            'optimistically increment a second local copy',
            handoff,
        )

    def test_overlays_check_then_remove_collected_items_and_cap_the_list(self):
        combined = COMBINED_OVERLAY.read_text(encoding='utf-8')
        collection = COLLECTION_OVERLAY.read_text(encoding='utf-8')
        for overlay in (combined, collection):
            self.assertIn('item-check-fade', overlay)
            self.assertIn("content: '✓'", overlay)
            self.assertIn("fetch(POLL_URL, {cache:'no-store'})", overlay)
            self.assertIn('more remaining', overlay)
        self.assertIn('MAX_OVERLAY_ITEMS = 10', combined)
        self.assertIn('MAX_VISIBLE_ITEMS = 14', collection)
        self.assertIn('renderOverlayItems(items)', combined)
        self.assertIn('renderItems(d.items || [])', collection)
