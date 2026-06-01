# QuestLog Web - Spotlight slot views
import time
import json
import random
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from app.db import get_db_session
from .models import WebSpotlightSlot, WebIndieGame, WebCommunity, WebUser
from .helpers import web_login_required, web_admin_required, add_web_user_context, sanitize_text

logger = logging.getLogger(__name__)


def _get_active_slot(db, category, slot_type):
    """Return active slot for category+type, or None if expired/missing."""
    now = int(time.time())
    slot = db.query(WebSpotlightSlot).filter(
        WebSpotlightSlot.category == category,
        WebSpotlightSlot.slot_type == slot_type,
        WebSpotlightSlot.starts_at <= now,
    ).filter(
        (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
    ).order_by(WebSpotlightSlot.created_at.desc()).first()
    return slot


def _serialize_indie(game):
    dev = None
    if game.dev_user:
        dev = {
            'username': game.dev_user.username,
            'avatar': game.dev_user.avatar_url or '',
        }
    return {
        'id': game.id,
        'slug': game.slug,
        'name': game.name,
        'cover_url': game.cover_url or '',
        'spotlight_quote': game.spotlight_quote or '',
        'dev': dev,
        'status': game.status,
    }


def _serialize_community(c):
    import re as _re
    slug = _re.sub(r'[^a-z0-9]+', '-', c.name.lower()).strip('-') if c.name else ''
    platform = c.platform.value if c.platform else 'discord'
    tags = []
    try:
        import json as _json
        tags = _json.loads(c.tags or '[]') if hasattr(c, 'tags') else []
    except Exception:
        pass
    return {
        'id': c.id,
        'name': c.name,
        'slug': slug,
        'icon_url': c.icon_url or '',
        'banner_url': c.banner_url or '' if hasattr(c, 'banner_url') else '',
        'short_description': c.short_description or '',
        'member_count': c.member_count or 0,
        'platform': platform,
        'invite_url': c.invite_url or '' if hasattr(c, 'invite_url') else '',
        'tags': tags[:5],
    }


def _serialize_creator(u):
    return {
        'id': u.id,
        'username': u.username,
        'avatar': u.avatar_url or '',
        'bio': u.bio or '',
    }


@require_http_methods(['GET'])
def api_spotlight(request):
    """
    Returns all active spotlight slots.
    ?category=indie|community|creator  (optional filter)
    ?slot_type=week|month|pool         (optional filter)
    """
    category_filter = request.GET.get('category', '').strip()
    slot_type_filter = request.GET.get('slot_type', '').strip()

    result = {}
    now = int(time.time())

    with get_db_session() as db:
        for category in ['indie', 'community', 'creator']:
            if category_filter and category_filter != category:
                continue
            result[category] = {}
            for slot_type in ['week', 'month', 'pool']:
                if slot_type_filter and slot_type_filter != slot_type:
                    continue

                if slot_type == 'pool':
                    # Random pick from pool - get all active pool entries for this category
                    pool_slots = db.query(WebSpotlightSlot).filter(
                        WebSpotlightSlot.category == category,
                        WebSpotlightSlot.slot_type == 'pool',
                        WebSpotlightSlot.starts_at <= now,
                    ).filter(
                        (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
                    ).all()

                    if not pool_slots:
                        result[category]['pool'] = None
                        continue

                    # Pick a random one and resolve the object
                    slot = random.choice(pool_slots)
                    obj = _resolve_slot_object(db, category, slot.ref_id)
                    result[category]['pool'] = obj

                else:
                    slot = _get_active_slot(db, category, slot_type)
                    if not slot:
                        result[category][slot_type] = None
                        continue
                    obj = _resolve_slot_object(db, category, slot.ref_id)
                    result[category][slot_type] = obj

    return JsonResponse(result)


def _resolve_slot_object(db, category, ref_id):
    """Resolve a spotlight slot's ref_id to a serialized object."""
    if category == 'indie':
        game = db.query(WebIndieGame).filter_by(id=ref_id, is_published=True).first()
        if not game:
            return None
        # eager load dev_user
        dev = db.query(WebUser).filter_by(id=game.dev_user_id).first() if game.dev_user_id else None
        game.dev_user = dev
        return _serialize_indie(game)
    elif category == 'community':
        c = db.query(WebCommunity).filter_by(id=ref_id).first()
        return _serialize_community(c) if c else None
    elif category == 'creator':
        u = db.query(WebUser).filter_by(id=ref_id, is_banned=False).first()
        return _serialize_creator(u) if u else None
    return None


@add_web_user_context
@web_admin_required
@require_http_methods(['POST'])
def api_spotlight_set(request):
    """
    Admin: set a spotlight slot.
    Body: { category, slot_type, ref_id, expires_at (optional unix ts) }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    category = data.get('category', '').strip()
    slot_type = data.get('slot_type', '').strip()
    ref_id = data.get('ref_id')
    expires_at = data.get('expires_at')  # unix timestamp or null

    if category not in ('indie', 'community', 'creator'):
        return JsonResponse({'error': 'Invalid category'}, status=400)
    if slot_type not in ('week', 'month', 'pool'):
        return JsonResponse({'error': 'Invalid slot_type'}, status=400)
    if not ref_id:
        return JsonResponse({'error': 'ref_id required'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        # For week/month: replace existing active slot (deactivate old one by setting expires_at=now)
        if slot_type in ('week', 'month'):
            old = db.query(WebSpotlightSlot).filter(
                WebSpotlightSlot.category == category,
                WebSpotlightSlot.slot_type == slot_type,
                WebSpotlightSlot.starts_at <= now,
            ).filter(
                (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
            ).all()
            for o in old:
                o.expires_at = now
            db.commit()

        # Calculate auto-expiry if not provided
        if not expires_at and slot_type in ('week', 'month'):
            import datetime
            dt = datetime.datetime.utcnow()
            if slot_type == 'week':
                # End of current Sunday (UTC)
                days_until_sunday = (6 - dt.weekday()) % 7 or 7
                end = dt + datetime.timedelta(days=days_until_sunday)
                end = end.replace(hour=23, minute=59, second=59)
            else:
                # End of current month
                if dt.month == 12:
                    end = dt.replace(year=dt.year+1, month=1, day=1) - datetime.timedelta(seconds=1)
                else:
                    end = dt.replace(month=dt.month+1, day=1) - datetime.timedelta(seconds=1)
            expires_at = int(end.timestamp())

        slot = WebSpotlightSlot(
            category=category,
            slot_type=slot_type,
            ref_id=ref_id,
            starts_at=now,
            expires_at=expires_at,
            set_by=request.web_user.id,
            created_at=now,
        )
        db.add(slot)
        db.commit()

    return JsonResponse({'ok': True})


@add_web_user_context
@web_admin_required
@require_http_methods(['DELETE'])
def api_spotlight_remove(request):
    """
    Admin: remove a spotlight slot.
    Body: { category, slot_type, ref_id } - for pool use ref_id, for week/month just category+slot_type
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    category = data.get('category', '').strip()
    slot_type = data.get('slot_type', '').strip()
    ref_id = data.get('ref_id')

    now = int(time.time())

    with get_db_session() as db:
        q = db.query(WebSpotlightSlot).filter(
            WebSpotlightSlot.category == category,
            WebSpotlightSlot.slot_type == slot_type,
        )
        if ref_id:
            q = q.filter(WebSpotlightSlot.ref_id == ref_id)
        slots = q.filter(
            (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
        ).all()
        for s in slots:
            s.expires_at = now
        db.commit()

    return JsonResponse({'ok': True})


@require_http_methods(['GET'])
def api_spotlight_pool_list(request):
    """
    Get current pool members for a category (for admin panel display).
    ?category=indie|community|creator
    """
    category = request.GET.get('category', 'indie').strip()
    now = int(time.time())

    with get_db_session() as db:
        pool_slots = db.query(WebSpotlightSlot).filter(
            WebSpotlightSlot.category == category,
            WebSpotlightSlot.slot_type == 'pool',
            WebSpotlightSlot.starts_at <= now,
        ).filter(
            (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
        ).all()

        items = []
        for slot in pool_slots:
            obj = _resolve_slot_object(db, category, slot.ref_id)
            if obj:
                obj['slot_id'] = slot.id
                items.append(obj)

    return JsonResponse({'pool': items})


COOLDOWN_SECONDS = 30 * 86400  # 30 days


@add_web_user_context
@web_admin_required
@require_http_methods(['POST'])
def api_spotlight_reroll(request):
    """Admin: randomly pick a new item for a slot, respecting cooldown and no-duplicate rules."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    category = data.get('category', '').strip()
    slot_type = data.get('slot_type', '').strip()

    if category not in ('indie', 'community', 'creator'):
        return JsonResponse({'error': 'Invalid category'}, status=400)
    if slot_type not in ('week', 'month'):
        return JsonResponse({'error': 'Invalid slot_type'}, status=400)

    other_slot = 'month' if slot_type == 'week' else 'week'
    now = int(time.time())
    cooldown_cutoff = now - COOLDOWN_SECONDS

    with get_db_session() as db:
        # Get the other slot's current ref_id (can't pick same item for both)
        other_active = _get_active_slot(db, category, other_slot)
        other_ref_id = other_active.ref_id if other_active else None

        # Get all ref_ids spotlighted within cooldown period
        recent_rows = db.query(WebSpotlightSlot.ref_id).filter(
            WebSpotlightSlot.category == category,
            WebSpotlightSlot.slot_type.in_(['week', 'month']),
            WebSpotlightSlot.starts_at >= cooldown_cutoff,
        ).all()
        on_cooldown = {r[0] for r in recent_rows}
        if other_ref_id:
            on_cooldown.add(other_ref_id)

        # Build candidate list
        if category == 'indie':
            from .models import WebIndieGame as _WIG
            all_ids = [g.id for g in db.query(_WIG).filter_by(is_published=True).all()]
        elif category == 'community':
            all_ids = [c.id for c in db.query(WebCommunity).filter_by(network_status='approved').all()]
        else:
            from .models import WebCreatorProfile as _WCP
            creator_uids = [r[0] for r in db.query(_WCP.user_id).filter_by(allow_discovery=True).all()]
            all_ids = [u.id for u in db.query(WebUser).filter(
                WebUser.id.in_(creator_uids),
                WebUser.is_banned == False,
                WebUser.is_hidden == False,
            ).all()] if creator_uids else []

        if not all_ids:
            return JsonResponse({'error': f'No {category} candidates found'}, status=400)

        eligible = [i for i in all_ids if i not in on_cooldown]
        if not eligible:
            eligible = [i for i in all_ids if i != other_ref_id] or all_ids

        ref_id = random.choice(eligible)

        # Expire current slot and set new one
        import datetime as _dt
        if slot_type == 'week':
            dt = _dt.datetime.utcnow()
            days_until_sunday = (6 - dt.weekday()) % 7 or 7
            end = (dt + _dt.timedelta(days=days_until_sunday)).replace(hour=23, minute=59, second=59)
            expires_at = int(end.timestamp())
        else:
            dt = _dt.datetime.utcnow()
            if dt.month == 12:
                end = dt.replace(year=dt.year + 1, month=1, day=1) - _dt.timedelta(seconds=1)
            else:
                end = dt.replace(month=dt.month + 1, day=1) - _dt.timedelta(seconds=1)
            expires_at = int(end.timestamp())

        # Expire old
        old = db.query(WebSpotlightSlot).filter(
            WebSpotlightSlot.category == category,
            WebSpotlightSlot.slot_type == slot_type,
        ).filter(
            (WebSpotlightSlot.expires_at == None) | (WebSpotlightSlot.expires_at > now)
        ).all()
        for o in old:
            o.expires_at = now

        slot = WebSpotlightSlot(
            category=category, slot_type=slot_type, ref_id=ref_id,
            starts_at=now, expires_at=expires_at,
            set_by=request.web_user.id, created_at=now,
        )
        db.add(slot)
        db.commit()

    return JsonResponse({'ok': True})


@add_web_user_context
@web_admin_required
@require_http_methods(['DELETE'])
def api_spotlight_remove_by_id(request):
    """Admin: remove a spotlight slot by its slot ID."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    slot_id = data.get('slot_id')
    if not slot_id:
        return JsonResponse({'error': 'slot_id required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        slot = db.query(WebSpotlightSlot).filter_by(id=slot_id).first()
        if slot:
            slot.expires_at = now
            db.commit()

    return JsonResponse({'ok': True})
