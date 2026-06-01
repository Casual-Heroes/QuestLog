"""
Auto-pick random spotlights for week/month slots.
Runs weekly (Monday) and monthly (1st of month).
Skips any slot that already has an active non-expired entry.
"""
import random
import time
import datetime
import logging

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import (
    WebIndieGame, WebCommunity, WebUser, WebCreatorProfile,
    WebSpotlightSlot,
)

logger = logging.getLogger(__name__)


def _end_of_week():
    """Unix timestamp for end of this Sunday (UTC)."""
    dt = datetime.datetime.utcnow()
    days_until_sunday = (6 - dt.weekday()) % 7 or 7
    end = (dt + datetime.timedelta(days=days_until_sunday)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    return int(end.timestamp())


def _end_of_month():
    """Unix timestamp for end of last day of this month (UTC)."""
    dt = datetime.datetime.utcnow()
    if dt.month == 12:
        end = dt.replace(year=dt.year + 1, month=1, day=1) - datetime.timedelta(seconds=1)
    else:
        end = dt.replace(month=dt.month + 1, day=1) - datetime.timedelta(seconds=1)
    return int(end.timestamp())


def _has_active_slot(db, category, slot_type):
    now = int(time.time())
    existing = db.query(WebSpotlightSlot).filter(
        WebSpotlightSlot.category == category,
        WebSpotlightSlot.slot_type == slot_type,
        WebSpotlightSlot.starts_at <= now,
    ).filter(
        (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
    ).first()
    return existing is not None


def _expire_slot(db, category, slot_type):
    now = int(time.time())
    old = db.query(WebSpotlightSlot).filter(
        WebSpotlightSlot.category == category,
        WebSpotlightSlot.slot_type == slot_type,
    ).filter(
        (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
    ).all()
    for o in old:
        o.expires_at = now


def _set_slot(db, category, slot_type, ref_id, expires_at, dry_run=False):
    now = int(time.time())
    if dry_run:
        logger.info('[DRY RUN] Would set %s %s -> ref_id=%s expires=%s', category, slot_type, ref_id, expires_at)
        return
    _expire_slot(db, category, slot_type)
    slot = WebSpotlightSlot(
        category=category,
        slot_type=slot_type,
        ref_id=ref_id,
        starts_at=now,
        expires_at=expires_at,
        set_by=None,
        created_at=now,
    )
    db.add(slot)
    db.commit()
    logger.info('Set spotlight %s %s -> ref_id=%s', category, slot_type, ref_id)


class Command(BaseCommand):
    help = 'Auto-pick random spotlights for week/month slots from published content.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Re-roll even if slot already set')
        parser.add_argument('--dry-run', action='store_true', help='Print what would be set without saving')
        parser.add_argument('--slot', choices=['week', 'month', 'both'], default='both')

    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']
        slot_arg = options['slot']

        now = datetime.datetime.utcnow()
        do_week = slot_arg in ('week', 'both')
        do_month = slot_arg in ('month', 'both')

        week_expires = _end_of_week()
        month_expires = _end_of_month()

        with get_db_session() as db:

            # ── INDIE GAME ───────────────────────────────────────────────
            indie_games = db.query(WebIndieGame).filter_by(is_published=True).all()
            if indie_games:
                if do_week and (force or not _has_active_slot(db, 'indie', 'week')):
                    pick = random.choice(indie_games)
                    _set_slot(db, 'indie', 'week', pick.id, week_expires, dry_run)
                    self.stdout.write(f'Indie week  -> {pick.name} (id={pick.id})')
                else:
                    self.stdout.write('Indie week  -> already set, skipping')

                if do_month and (force or not _has_active_slot(db, 'indie', 'month')):
                    pick = random.choice(indie_games)
                    _set_slot(db, 'indie', 'month', pick.id, month_expires, dry_run)
                    self.stdout.write(f'Indie month -> {pick.name} (id={pick.id})')
                else:
                    self.stdout.write('Indie month -> already set, skipping')
            else:
                self.stdout.write('Indie: no published games found')

            # ── COMMUNITY ────────────────────────────────────────────────
            communities = db.query(WebCommunity).filter_by(network_status='approved').all()
            if communities:
                if do_week and (force or not _has_active_slot(db, 'community', 'week')):
                    pick = random.choice(communities)
                    _set_slot(db, 'community', 'week', pick.id, week_expires, dry_run)
                    self.stdout.write(f'Community week  -> {pick.name} (id={pick.id})')
                else:
                    self.stdout.write('Community week  -> already set, skipping')

                if do_month and (force or not _has_active_slot(db, 'community', 'month')):
                    pick = random.choice(communities)
                    _set_slot(db, 'community', 'month', pick.id, month_expires, dry_run)
                    self.stdout.write(f'Community month -> {pick.name} (id={pick.id})')
                else:
                    self.stdout.write('Community month -> already set, skipping')
            else:
                self.stdout.write('Community: no approved communities found')

            # ── CREATOR ──────────────────────────────────────────────────
            creator_user_ids = [
                r[0] for r in db.query(WebCreatorProfile.user_id).filter_by(allow_discovery=True).all()
            ]
            creators = db.query(WebUser).filter(
                WebUser.id.in_(creator_user_ids),
                WebUser.is_banned == False,
                WebUser.is_hidden == False,
            ).all() if creator_user_ids else []

            if creators:
                if do_week and (force or not _has_active_slot(db, 'creator', 'week')):
                    pick = random.choice(creators)
                    _set_slot(db, 'creator', 'week', pick.id, week_expires, dry_run)
                    self.stdout.write(f'Creator week  -> {pick.username} (id={pick.id})')
                else:
                    self.stdout.write('Creator week  -> already set, skipping')

                if do_month and (force or not _has_active_slot(db, 'creator', 'month')):
                    pick = random.choice(creators)
                    _set_slot(db, 'creator', 'month', pick.id, month_expires, dry_run)
                    self.stdout.write(f'Creator month -> {pick.username} (id={pick.id})')
                else:
                    self.stdout.write('Creator month -> already set, skipping')
            else:
                self.stdout.write('Creator: no discoverable creators found')

        self.stdout.write(self.style.SUCCESS('rotate_spotlights done'))
