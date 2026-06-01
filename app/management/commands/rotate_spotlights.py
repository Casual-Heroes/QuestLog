"""
Auto-pick random spotlights for week/month slots.
Rules:
- Same item cannot hold both week AND month at the same time.
- Cooldown: once spotlighted, an item cannot be picked again for COOLDOWN_DAYS.
- Skips any slot that already has an active non-expired entry (unless --force).
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

# How long (days) before a spotlighted item is eligible again
COOLDOWN_DAYS = 30


def _end_of_week():
    dt = datetime.datetime.utcnow()
    days_until_sunday = (6 - dt.weekday()) % 7 or 7
    end = (dt + datetime.timedelta(days=days_until_sunday)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    return int(end.timestamp())


def _end_of_month():
    dt = datetime.datetime.utcnow()
    if dt.month == 12:
        end = dt.replace(year=dt.year + 1, month=1, day=1) - datetime.timedelta(seconds=1)
    else:
        end = dt.replace(month=dt.month + 1, day=1) - datetime.timedelta(seconds=1)
    return int(end.timestamp())


def _has_active_slot(db, category, slot_type):
    now = int(time.time())
    return db.query(WebSpotlightSlot).filter(
        WebSpotlightSlot.category == category,
        WebSpotlightSlot.slot_type == slot_type,
        WebSpotlightSlot.starts_at <= now,
    ).filter(
        (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
    ).first() is not None


def _get_active_ref_id(db, category, slot_type):
    """Return the ref_id of the currently active slot, or None."""
    now = int(time.time())
    slot = db.query(WebSpotlightSlot).filter(
        WebSpotlightSlot.category == category,
        WebSpotlightSlot.slot_type == slot_type,
        WebSpotlightSlot.starts_at <= now,
    ).filter(
        (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
    ).first()
    return slot.ref_id if slot else None


def _get_recently_spotlighted(db, category):
    """Return set of ref_ids spotlighted within COOLDOWN_DAYS across both slots."""
    cutoff = int(time.time()) - (COOLDOWN_DAYS * 86400)
    rows = db.query(WebSpotlightSlot.ref_id).filter(
        WebSpotlightSlot.category == category,
        WebSpotlightSlot.slot_type.in_(['week', 'month']),
        WebSpotlightSlot.starts_at >= cutoff,
    ).all()
    return {r[0] for r in rows}


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
        logger.info('[DRY RUN] Would set %s %s -> ref_id=%s', category, slot_type, ref_id)
        return
    from sqlalchemy import text as _text
    _expire_slot(db, category, slot_type)
    db.execute(_text("""
        INSERT INTO web_spotlight_slots (category, slot_type, ref_id, starts_at, expires_at, set_by, created_at)
        VALUES (:cat, :st, :rid, :sa, :ea, 1, :ca)
    """), {'cat': category, 'st': slot_type, 'rid': ref_id, 'sa': now, 'ea': expires_at, 'ca': now})
    db.commit()
    logger.info('Set spotlight %s %s -> ref_id=%s', category, slot_type, ref_id)


def _pick(candidates, exclude_ids, category_label, stdout):
    """Pick randomly from candidates, excluding any in exclude_ids. Falls back to full pool if needed."""
    eligible = [c for c in candidates if c not in exclude_ids]
    if not eligible:
        stdout.write(f'  [{category_label}] All candidates on cooldown - picking from full pool')
        eligible = candidates
    if not eligible:
        return None
    return random.choice(eligible)


class Command(BaseCommand):
    help = 'Auto-pick random spotlights respecting cooldown and no-duplicate-slot rules.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Re-roll even if slot already set')
        parser.add_argument('--dry-run', action='store_true', help='Print picks without saving')
        parser.add_argument('--slot', choices=['week', 'month', 'both'], default='both')

    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']
        slot_arg = options['slot']

        do_week = slot_arg in ('week', 'both')
        do_month = slot_arg in ('month', 'both')

        week_expires = _end_of_week()
        month_expires = _end_of_month()

        with get_db_session() as db:

            # ── INDIE GAME ───────────────────────────────────────────────
            indie_ids = [g.id for g in db.query(WebIndieGame).filter_by(is_published=True).all()]
            indie_names = {g.id: g.name for g in db.query(WebIndieGame).filter_by(is_published=True).all()}
            if indie_ids:
                recent = _get_recently_spotlighted(db, 'indie')
                week_id = _get_active_ref_id(db, 'indie', 'week')
                month_id = _get_active_ref_id(db, 'indie', 'month')

                if do_week and (force or not _has_active_slot(db, 'indie', 'week')):
                    # Exclude: cooldown + current month pick (can't hold both)
                    exclude = recent | ({month_id} if month_id else set())
                    pick = _pick(indie_ids, exclude, 'Indie week', self.stdout)
                    if pick:
                        _set_slot(db, 'indie', 'week', pick, week_expires, dry_run)
                        self.stdout.write(f'Indie week  -> {indie_names.get(pick)} (id={pick})')
                        week_id = pick
                else:
                    self.stdout.write('Indie week  -> already set, skipping')

                if do_month and (force or not _has_active_slot(db, 'indie', 'month')):
                    # Exclude: cooldown + current week pick (can't hold both)
                    exclude = recent | ({week_id} if week_id else set())
                    pick = _pick(indie_ids, exclude, 'Indie month', self.stdout)
                    if pick:
                        _set_slot(db, 'indie', 'month', pick, month_expires, dry_run)
                        self.stdout.write(f'Indie month -> {indie_names.get(pick)} (id={pick})')
                else:
                    self.stdout.write('Indie month -> already set, skipping')
            else:
                self.stdout.write('Indie: no published games found')

            # ── COMMUNITY ────────────────────────────────────────────────
            comm_objs = db.query(WebCommunity).filter_by(network_status='approved').all()
            comm_ids = [c.id for c in comm_objs]
            comm_names = {c.id: c.name for c in comm_objs}
            if comm_ids:
                recent = _get_recently_spotlighted(db, 'community')
                week_id = _get_active_ref_id(db, 'community', 'week')
                month_id = _get_active_ref_id(db, 'community', 'month')

                if do_week and (force or not _has_active_slot(db, 'community', 'week')):
                    exclude = recent | ({month_id} if month_id else set())
                    pick = _pick(comm_ids, exclude, 'Community week', self.stdout)
                    if pick:
                        _set_slot(db, 'community', 'week', pick, week_expires, dry_run)
                        self.stdout.write(f'Community week  -> {comm_names.get(pick)} (id={pick})')
                        week_id = pick
                else:
                    self.stdout.write('Community week  -> already set, skipping')

                if do_month and (force or not _has_active_slot(db, 'community', 'month')):
                    exclude = recent | ({week_id} if week_id else set())
                    pick = _pick(comm_ids, exclude, 'Community month', self.stdout)
                    if pick:
                        _set_slot(db, 'community', 'month', pick, month_expires, dry_run)
                        self.stdout.write(f'Community month -> {comm_names.get(pick)} (id={pick})')
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
            creator_ids = [u.id for u in creators]
            creator_names = {u.id: u.username for u in creators}

            if creator_ids:
                recent = _get_recently_spotlighted(db, 'creator')
                week_id = _get_active_ref_id(db, 'creator', 'week')
                month_id = _get_active_ref_id(db, 'creator', 'month')

                if do_week and (force or not _has_active_slot(db, 'creator', 'week')):
                    exclude = recent | ({month_id} if month_id else set())
                    pick = _pick(creator_ids, exclude, 'Creator week', self.stdout)
                    if pick:
                        _set_slot(db, 'creator', 'week', pick, week_expires, dry_run)
                        self.stdout.write(f'Creator week  -> {creator_names.get(pick)} (id={pick})')
                        week_id = pick
                else:
                    self.stdout.write('Creator week  -> already set, skipping')

                if do_month and (force or not _has_active_slot(db, 'creator', 'month')):
                    exclude = recent | ({week_id} if week_id else set())
                    pick = _pick(creator_ids, exclude, 'Creator month', self.stdout)
                    if pick:
                        _set_slot(db, 'creator', 'month', pick, month_expires, dry_run)
                        self.stdout.write(f'Creator month -> {creator_names.get(pick)} (id={pick})')
                else:
                    self.stdout.write('Creator month -> already set, skipping')
            else:
                self.stdout.write('Creator: no discoverable creators found')

        self.stdout.write(self.style.SUCCESS('rotate_spotlights done'))
