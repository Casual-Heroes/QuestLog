"""Widen and repair Soulslike Fury/Hollow counters without deleting run data."""

from django.core.management.base import BaseCommand, CommandError
from sqlalchemy import text

from app.db import get_engine
from app.questlog_web.views_soulslike import _rage_from_event_history


_COUNTER_COLUMNS = ('hollow_streak', 'hollow_boss_kills')


class Command(BaseCommand):
    help = (
        'Widen Soulslike Hollow counters to BIGINT UNSIGNED and rebuild them '
        'from existing death/boss events.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='Also rebuild ended sessions (active sessions are rebuilt by default).',
        )
        parser.add_argument(
            '--schema-only',
            action='store_true',
            help='Widen the columns but do not rebuild counters from event history.',
        )

    def handle(self, *args, **options):
        engine = get_engine()

        # MySQL ALTER TABLE preserves every row and is idempotent here. The
        # identifiers are constants above, never command/user input.
        with engine.begin() as db:
            for column in _COUNTER_COLUMNS:
                metadata = db.execute(text("""
                    SELECT DATA_TYPE, COLUMN_TYPE
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE()
                      AND TABLE_NAME='sl_collection_sessions'
                      AND COLUMN_NAME=:column
                """), {'column': column}).mappings().one_or_none()
                if metadata is None:
                    raise CommandError(
                        f'sl_collection_sessions.{column} does not exist'
                    )
                data_type = str(metadata['DATA_TYPE']).lower()
                column_type = str(metadata['COLUMN_TYPE']).lower()
                if data_type == 'bigint' and 'unsigned' in column_type:
                    self.stdout.write(f'{column}: already BIGINT UNSIGNED')
                    continue
                db.execute(text(
                    'ALTER TABLE sl_collection_sessions '
                    f'MODIFY COLUMN {column} BIGINT UNSIGNED NOT NULL DEFAULT 0'
                ))
                self.stdout.write(self.style.SUCCESS(
                    f'{column}: widened to BIGINT UNSIGNED'
                ))

        if options['schema_only']:
            return

        scope = '' if options['all'] else 'WHERE ended_at IS NULL'
        rebuilt_count = 0
        with engine.begin() as db:
            session_ids = db.execute(text(
                f'SELECT id FROM sl_collection_sessions {scope} ORDER BY id'
            )).scalars().all()

            for session_id in session_ids:
                death_times = db.execute(text("""
                    SELECT died_at
                    FROM sl_death_events
                    WHERE session_id=:sid
                      AND COALESCE(area_name, '') <> '__session_adjustment__'
                    ORDER BY died_at, id
                """), {'sid': session_id}).scalars().all()
                boss_events = db.execute(text("""
                    SELECT defeated_at, tier
                    FROM sl_session_bosses
                    WHERE session_id=:sid
                      AND is_defeated=1
                      AND defeated_at IS NOT NULL
                    ORDER BY defeated_at, boss_key
                """), {'sid': session_id}).all()
                rebuilt = _rage_from_event_history(death_times, boss_events)
                db.execute(text("""
                    UPDATE sl_collection_sessions
                    SET rage_pct=:rage_pct,
                        rage_name=:rage_name,
                        hollow_streak=:hollow_streak,
                        hollow_entered_at=:hollow_entered_at,
                        time_in_hollow_sec=:time_in_hollow_sec,
                        hollow_boss_kills=:hollow_boss_kills
                    WHERE id=:sid
                """), {
                    'rage_pct': rebuilt['rage_pct'],
                    'rage_name': rebuilt['rage_name'],
                    'hollow_streak': rebuilt['hollow_streak'],
                    'hollow_entered_at': rebuilt['hollow_entered_at'],
                    'time_in_hollow_sec': rebuilt['time_in_hollow_sec'],
                    'hollow_boss_kills': rebuilt['hollow_boss_kills'],
                    'sid': session_id,
                })
                rebuilt_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Rebuilt Fury/Hollow state for {rebuilt_count} session(s); no rows deleted.'
        ))
