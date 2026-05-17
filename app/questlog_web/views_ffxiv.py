import json
import time
import math
import re
import logging
import requests
from datetime import datetime, timezone, timedelta
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from app.db import get_db_session
from app.questlog_web.models import WebLFGGroup, WebLFGMember, WebUser, WebFfxivCharacter, WebFfxivAchievementReward, WebFfxivClear
from app.questlog_web.helpers import get_web_user, sanitize_text, web_login_required, add_web_user_context, award_xp, award_legacy
from sqlalchemy import desc

logger = logging.getLogger(__name__)

_LODESTONE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}
_LODESTONE_BASE = 'https://na.finalfantasyxiv.com/lodestone'
_FFXIV_COLLECT_BASE = 'https://ffxivcollect.com/api'
_CH_FC_NAME = 'Casual Heroes'  # In-game FC name - used for auto-gate once FC is built


def _is_fc_member(db, user_id):
    """
    Returns True if the user is allowed to write to FC progression.
    Gate: manual is_ffxiv_member flag OR linked character is in the CH in-game FC.
    The FC auto-gate activates automatically once members join the in-game FC.
    """
    user = db.query(WebUser).filter_by(id=user_id).first()
    if not user:
        return False
    if user.is_ffxiv_member:
        return True
    # Auto-gate: check if their linked character is in the CH FC
    char = db.query(WebFfxivCharacter).filter_by(user_id=user_id, is_primary=True).first()
    if char and char.free_company and _CH_FC_NAME.lower() in char.free_company.lower():
        return True
    return False

# ---------------------------------------------------------------------------
# Ocean Fishing Schedule Calculator
# ---------------------------------------------------------------------------
#
# Ocean Fishing departs every 2 real hours from Limsa Lominsa.
# Registration opens 15 min before each window.
# The route cycles deterministically based on the epoch window index.
#
# Route cycle (repeats every 8 windows = 16 hours):
#   Window 0: Indigo Route - Evening  (stop times: Sunset, Night, Night)
#   Window 1: Ruby Route   - Night    (stop times: Night, Night, Sunset)
#   Window 2: Indigo Route - Night    (stop times: Night, Night, Night)
#   Window 3: Ruby Route   - Day      (stop times: Day, Sunset, Night)
#   Window 4: Indigo Route - Day      (stop times: Day, Day, Sunset)
#   Window 5: Ruby Route   - Sunset   (stop times: Sunset, Night, Night)
#   Window 6: Indigo Route - Sunset   (stop times: Sunset, Sunset, Night)
#   Window 7: Ruby Route   - Morning  (stop times: Morning, Day, Sunset)
#
# Each route has 3 stops. Stop fish depends on route + time of day.
#
# Reference epoch anchor: window 0 started at Unix 0 (adjusted below).
# Actual anchor: 2021-10-12 00:00:00 UTC = window index 0 for Indigo Evening.
# Epoch seconds for that timestamp: 1633996800

_OF_EPOCH_ANCHOR = 1634270400  # 2021-10-15 00:00:00 UTC, window 0 = Indigo Evening
_OF_WINDOW_DURATION = 7200     # 2 hours in seconds
_OF_REGISTRATION_OFFSET = 900  # 15 min before departure

_OF_ROUTES = [
    {
        'id': 0,
        'name': 'Indigo Route',
        'label': 'Indigo',
        'color': 'indigo',
        'description': 'Western Eorzean seas',
        'stops': ['The Rothlyt Sound', 'The Northern Strait of Merlthor', 'Galadion Bay'],
        'times': ['Evening', 'Night', 'Night'],
        'spectral': 'Spectral Current',
        'blue_fish': ['Coral Manta', 'Hafgufa', 'Sothis'],
        'achievement_fish': [
            {'name': 'Coral Manta', 'stop': 1, 'time': 'Evening/Night', 'bait': 'Glowworm -> Versatile Lure'},
            {'name': 'Hafgufa', 'stop': 2, 'time': 'Night', 'bait': 'Squid Strip -> Glowworm'},
            {'name': 'Sothis', 'stop': 3, 'time': 'Night', 'bait': 'Railed Frog -> Versatile Lure'},
        ],
    },
    {
        'id': 1,
        'name': 'Ruby Route',
        'label': 'Ruby',
        'color': 'red',
        'description': 'Far Eastern seas',
        'stops': ['Outer Galadion Bay', 'The Southern Strait of Merlthor', 'The Cieldalaes'],
        'times': ['Night', 'Night', 'Sunset'],
        'spectral': 'Spectral Current',
        'blue_fish': ['Stonescale', 'Coralhorn Seahorse', 'Kuno the Killer'],
        'achievement_fish': [
            {'name': 'Stonescale', 'stop': 1, 'time': 'Night', 'bait': 'Krill Cage Feeder -> Versatile Lure'},
            {'name': 'Coralhorn Seahorse', 'stop': 2, 'time': 'Night', 'bait': 'Plump Worm -> Krill Cage Feeder'},
            {'name': 'Kuno the Killer', 'stop': 3, 'time': 'Sunset', 'bait': 'Glowworm -> Versatile Lure'},
        ],
    },
    {
        'id': 2,
        'name': 'Indigo Route',
        'label': 'Indigo',
        'color': 'indigo',
        'description': 'Western Eorzean seas',
        'stops': ['The Rothlyt Sound', 'The Northern Strait of Merlthor', 'Galadion Bay'],
        'times': ['Night', 'Night', 'Night'],
        'spectral': 'Spectral Current',
        'blue_fish': ['Hafgufa', 'Sothis'],
        'achievement_fish': [
            {'name': 'Hafgufa', 'stop': 2, 'time': 'Night', 'bait': 'Squid Strip -> Glowworm'},
            {'name': 'Sothis', 'stop': 3, 'time': 'Night', 'bait': 'Railed Frog -> Versatile Lure'},
        ],
    },
    {
        'id': 3,
        'name': 'Ruby Route',
        'label': 'Ruby',
        'color': 'red',
        'description': 'Far Eastern seas',
        'stops': ['Outer Galadion Bay', 'The Southern Strait of Merlthor', 'The Cieldalaes'],
        'times': ['Day', 'Sunset', 'Night'],
        'spectral': 'Spectral Current',
        'blue_fish': ['Stonescale'],
        'achievement_fish': [
            {'name': 'Stonescale', 'stop': 1, 'time': 'Day', 'bait': 'Krill Cage Feeder -> Versatile Lure'},
        ],
    },
    {
        'id': 4,
        'name': 'Indigo Route',
        'label': 'Indigo',
        'color': 'indigo',
        'description': 'Western Eorzean seas',
        'stops': ['The Rothlyt Sound', 'The Northern Strait of Merlthor', 'Galadion Bay'],
        'times': ['Day', 'Day', 'Sunset'],
        'spectral': 'Spectral Current',
        'blue_fish': ['Coral Manta'],
        'achievement_fish': [
            {'name': 'Coral Manta', 'stop': 1, 'time': 'Day', 'bait': 'Glowworm -> Versatile Lure'},
        ],
    },
    {
        'id': 5,
        'name': 'Ruby Route',
        'label': 'Ruby',
        'color': 'red',
        'description': 'Far Eastern seas',
        'stops': ['Outer Galadion Bay', 'The Southern Strait of Merlthor', 'The Cieldalaes'],
        'times': ['Sunset', 'Night', 'Night'],
        'spectral': 'Spectral Current',
        'blue_fish': ['Kuno the Killer', 'Coralhorn Seahorse'],
        'achievement_fish': [
            {'name': 'Kuno the Killer', 'stop': 1, 'time': 'Sunset', 'bait': 'Glowworm -> Versatile Lure'},
            {'name': 'Coralhorn Seahorse', 'stop': 2, 'time': 'Night', 'bait': 'Plump Worm -> Krill Cage Feeder'},
        ],
    },
    {
        'id': 6,
        'name': 'Indigo Route',
        'label': 'Indigo',
        'color': 'indigo',
        'description': 'Western Eorzean seas',
        'stops': ['The Rothlyt Sound', 'The Northern Strait of Merlthor', 'Galadion Bay'],
        'times': ['Sunset', 'Sunset', 'Night'],
        'spectral': 'Spectral Current',
        'blue_fish': ['Coral Manta', 'Hafgufa'],
        'achievement_fish': [
            {'name': 'Coral Manta', 'stop': 1, 'time': 'Sunset', 'bait': 'Glowworm -> Versatile Lure'},
            {'name': 'Hafgufa', 'stop': 2, 'time': 'Sunset', 'bait': 'Squid Strip -> Glowworm'},
        ],
    },
    {
        'id': 7,
        'name': 'Ruby Route',
        'label': 'Ruby',
        'color': 'red',
        'description': 'Far Eastern seas',
        'stops': ['Outer Galadion Bay', 'The Southern Strait of Merlthor', 'The Cieldalaes'],
        'times': ['Morning', 'Day', 'Sunset'],
        'spectral': 'Spectral Current',
        'blue_fish': [],
        'achievement_fish': [],
    },
]

_OF_TIME_ICONS = {
    'Morning': 'fa-sun',
    'Day':     'fa-sun',
    'Sunset':  'fa-cloud-sun',
    'Evening': 'fa-moon',
    'Night':   'fa-moon',
}

_OF_TIME_COLORS = {
    'Morning': 'text-yellow-300',
    'Day':     'text-yellow-400',
    'Sunset':  'text-orange-400',
    'Evening': 'text-indigo-400',
    'Night':   'text-blue-400',
}


def _get_window_index(unix_ts):
    """Return which 2-hour window index (0-7) the given unix timestamp falls in."""
    elapsed = unix_ts - _OF_EPOCH_ANCHOR
    window_num = elapsed // _OF_WINDOW_DURATION
    return int(window_num % 8), int(window_num)


def _window_start(window_num):
    """Return the unix timestamp when a given absolute window number starts."""
    return _OF_EPOCH_ANCHOR + window_num * _OF_WINDOW_DURATION


def _build_schedule(count=8):
    """Return the next `count` ocean fishing windows with full metadata."""
    now = int(time.time())
    elapsed = now - _OF_EPOCH_ANCHOR
    current_window_num = elapsed // _OF_WINDOW_DURATION
    # If registration is still open for current window, include it
    current_start = _window_start(current_window_num)
    reg_opens = current_start - _OF_REGISTRATION_OFFSET

    if now >= reg_opens:
        start_window = current_window_num
    else:
        start_window = current_window_num - 1

    windows = []
    for i in range(count):
        wnum = start_window + i
        wstart = _window_start(wnum)
        widx = int(wnum % 8)
        route = _OF_ROUTES[widx]
        reg_open_ts = wstart - _OF_REGISTRATION_OFFSET
        is_current = (wnum == current_window_num)
        is_active = (wstart <= now < wstart + _OF_WINDOW_DURATION)
        reg_open = reg_open_ts <= now < wstart

        windows.append({
            'window_num':   wnum,
            'route':        route,
            'departure_ts': wstart,
            'reg_opens_ts': reg_open_ts,
            'is_current':   is_current,
            'is_active':    is_active,
            'reg_open':     reg_open,
        })
    return windows


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@add_web_user_context
def ffxiv_tools_hub(request):
    """Landing page for all FFXIV tools."""
    web_user = get_web_user(request)
    linked_character = None
    if web_user:
        with get_db_session() as db:
            linked_character = db.query(WebFfxivCharacter).filter_by(
                user_id=web_user.id, is_primary=True
            ).first()
            if linked_character is None:
                linked_character = db.query(WebFfxivCharacter).filter_by(
                    user_id=web_user.id
                ).order_by(WebFfxivCharacter.id.asc()).first()
            if linked_character:
                linked_character = {
                    'name': linked_character.character_name,
                    'world': linked_character.world,
                    'avatar': linked_character.avatar_url,
                    'lodestone_id': linked_character.lodestone_id,
                }
    return render(request, 'questlog_web/ffxiv_tools_hub.html', {
        'web_user': web_user,
        'active_page': 'ffxiv_tools',
        'linked_character': linked_character,
    })


@add_web_user_context
def ffxiv_gathering(request):
    """Gathering timers - live Eorzea clock + timed node schedule."""
    web_user = get_web_user(request)
    return render(request, 'questlog_web/ffxiv_gathering.html', {
        'web_user': web_user,
        'active_page': 'ffxiv_gathering',
    })


@add_web_user_context
def ffxiv_fc(request):
    """FC Progression - CH members with linked characters, mount/minion farming, raid clears."""
    web_user = get_web_user(request)
    web_user_id = request.session.get('web_user_id')

    members = []
    my_clears = []
    # Map of user_id -> set of content_keys for all members
    all_clears = {}

    with get_db_session() as db:
        rows = db.query(WebFfxivCharacter, WebUser).join(
            WebUser, WebFfxivCharacter.user_id == WebUser.id
        ).filter(
            WebFfxivCharacter.sync_status == 'ok',
            WebFfxivCharacter.is_primary == True,
            WebUser.is_banned == False,
        ).order_by(WebFfxivCharacter.character_name.asc()).all()

        for char, user in rows:
            mounts = json.loads(char.mounts_json or '[]')
            minions = json.loads(char.minions_json or '[]')
            members.append({
                'user_id':        user.id,
                'username':       user.username,
                'display_name':   user.display_name or user.username,
                'avatar':         user.avatar_url or '',
                'char_name':      char.character_name,
                'world':          char.world,
                'datacenter':     char.datacenter,
                'free_company':   char.free_company or '',
                'fc_tag':         char.fc_tag or '',
                'active_job':     char.active_job or '',
                'char_avatar':    char.avatar_url or '',
                'mount_count':    len(mounts),
                'minion_count':   len(minions),
                'mounts':         mounts,
                'minions':        minions,
                'last_synced':    char.last_synced_at or 0,
            })

        # Load all clears for all members in one query
        member_ids = [m['user_id'] for m in members]
        if member_ids:
            clear_rows = db.query(WebFfxivClear).filter(
                WebFfxivClear.user_id.in_(member_ids)
            ).all()
            for c in clear_rows:
                if c.user_id not in all_clears:
                    all_clears[c.user_id] = []
                all_clears[c.user_id].append(c.content_key)
                if web_user_id and c.user_id == web_user_id:
                    my_clears.append(c.content_key)

    # Attach clears list to each member
    for m in members:
        m['clears'] = all_clears.get(m['user_id'], [])

    # Check if the current user has FC write access
    user_is_fc_member = False
    if web_user_id:
        with get_db_session() as db:
            user_is_fc_member = _is_fc_member(db, web_user_id)

    return render(request, 'questlog_web/ffxiv_fc.html', {
        'web_user':          web_user,
        'active_page':       'ffxiv_fc',
        'members':           json.dumps(members),
        'member_count':      len(members),
        'my_clears':         json.dumps(my_clears),
        'user_is_fc_member': user_is_fc_member,
    })


@web_login_required
@require_POST
def api_ffxiv_toggle_clear(request, content_key):
    """Toggle a raid/content clear on or off for the logged-in user."""
    web_user_id = request.session.get('web_user_id')
    if not web_user_id:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    # Validate content_key: alphanumeric + underscores, max 32 chars
    if not re.match(r'^[a-z0-9_]{1,32}$', content_key):
        return JsonResponse({'error': 'Invalid content key'}, status=400)

    with get_db_session() as db:
        if not _is_fc_member(db, web_user_id):
            return JsonResponse({'error': 'FC members only - ask an admin to grant access.'}, status=403)

        existing = db.query(WebFfxivClear).filter_by(
            user_id=web_user_id, content_key=content_key
        ).first()
        if existing:
            db.delete(existing)
            db.commit()
            return JsonResponse({'cleared': False})
        else:
            new_clear = WebFfxivClear(
                user_id=web_user_id,
                content_key=content_key,
                cleared_at=int(time.time()),
            )
            db.add(new_clear)
            db.commit()
            return JsonResponse({'cleared': True})


@add_web_user_context
def ffxiv_resets(request):
    """Daily & weekly reset checklist."""
    web_user = get_web_user(request)
    return render(request, 'questlog_web/ffxiv_resets.html', {
        'web_user': web_user,
        'active_page': 'ffxiv_resets',
    })


@add_web_user_context
def ffxiv_ocean_fishing(request):
    """Ocean fishing schedule and group-up hub."""
    web_user = get_web_user(request)
    schedule = _build_schedule(8)

    # Attach "going" count and current user's RSVP status per window
    web_user_id = request.session.get('web_user_id')
    with get_db_session() as db:
        for win in schedule:
            # LFG groups for ocean fishing this window
            groups = db.query(WebLFGGroup).filter(
                WebLFGGroup.game_name == 'ffxiv',
                WebLFGGroup.scheduled_time == win['departure_ts'],
                WebLFGGroup.status == 'open',
                WebLFGGroup.title.like('Ocean Fishing%'),
            ).all()
            going_users = []
            user_going = False
            for g in groups:
                members = db.query(WebLFGMember).filter_by(group_id=g.id).all()
                for m in members:
                    u = db.query(WebUser).filter_by(id=m.user_id).first()
                    if u:
                        going_users.append({
                            'display_name': u.display_name or u.username,
                            'avatar_url': u.avatar_url,
                            'user_id': u.id,
                        })
                    if m.user_id == web_user_id:
                        user_going = True
            win['going_users'] = going_users
            win['going_count'] = len(going_users)
            win['user_going'] = user_going

    return render(request, 'questlog_web/ffxiv_ocean_fishing.html', {
        'web_user': web_user,
        'active_page': 'ffxiv_ocean_fishing',
        'schedule': schedule,
        'schedule_json': json.dumps([
            {
                'window_num':   w['window_num'],
                'departure_ts': w['departure_ts'],
                'reg_opens_ts': w['reg_opens_ts'],
                'route_name':   w['route']['name'],
                'route_label':  w['route']['label'],
                'route_color':  w['route']['color'],
                'stops':        w['route']['stops'],
                'times':        w['route']['times'],
                'blue_fish':    w['route']['blue_fish'],
                'is_active':    w['is_active'],
                'reg_open':     w['reg_open'],
            }
            for w in schedule
        ]),
        'time_icons': _OF_TIME_ICONS,
        'time_colors': _OF_TIME_COLORS,
    })


@require_POST
@web_login_required
def api_ffxiv_ocean_fishing_rsvp(request):
    """Toggle RSVP for an ocean fishing window."""
    web_user_id = request.session.get('web_user_id')
    try:
        data = json.loads(request.body)
        window_num = int(data.get('window_num', 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request'}, status=400)

    departure_ts = _window_start(window_num)
    now = int(time.time())

    # Don't allow RSVPs for windows in the past
    if departure_ts < now - _OF_WINDOW_DURATION:
        return JsonResponse({'error': 'That window has already passed'}, status=400)

    with get_db_session() as db:
        # Find or create the ocean fishing LFG group for this window
        # Title prefix "Ocean Fishing" lets us identify these groups
        group = db.query(WebLFGGroup).filter(
            WebLFGGroup.game_name == 'ffxiv',
            WebLFGGroup.scheduled_time == departure_ts,
            WebLFGGroup.status == 'open',
            WebLFGGroup.title.like('Ocean Fishing%'),
        ).first()

        if not group:
            widx = int(window_num % 8)
            route = _OF_ROUTES[widx]
            user = db.query(WebUser).filter_by(id=web_user_id).first()
            if not user:
                return JsonResponse({'error': 'User not found'}, status=400)
            now_ts = int(time.time())
            # Look up FFXIV cover from IGDB (same as LFG create flow)
            ffxiv_cover_url = None
            ffxiv_game_id = None
            try:
                import asyncio as _asyncio
                from app.utils.igdb import search_games as _igdb_search
                _loop = _asyncio.new_event_loop()
                try:
                    _results = _loop.run_until_complete(_igdb_search('Final Fantasy XIV Online', limit=1))
                finally:
                    _loop.close()
                if _results:
                    ffxiv_cover_url = _results[0].cover_url
                    ffxiv_game_id = str(_results[0].id) if _results[0].id else None
            except Exception as _e:
                logger.warning(f'IGDB lookup failed for ocean fishing group: {_e}')

            group = WebLFGGroup(
                creator_id=web_user_id,
                game_name='ffxiv',
                game_id=ffxiv_game_id,
                game_image_url=ffxiv_cover_url,
                title=f'Ocean Fishing - {route["name"]}',
                description=f'{route["name"]} ({" / ".join(route["times"])}). Auto-created group for the {datetime.fromtimestamp(departure_ts, tz=timezone.utc).strftime("%b %d %H:%M")} UTC departure.',
                scheduled_time=departure_ts,
                group_size=24,
                current_size=0,
                use_roles=False,
                status='open',
                created_at=now_ts,
                updated_at=now_ts,
            )
            db.add(group)
            db.flush()

        # Toggle membership
        existing = db.query(WebLFGMember).filter_by(
            group_id=group.id, user_id=web_user_id
        ).first()

        if existing:
            db.delete(existing)
            going = False
        else:
            is_creator = group.creator_id == web_user_id
            member = WebLFGMember(
                group_id=group.id,
                user_id=web_user_id,
                role='dps',
                is_creator=is_creator,
                status='joined',
                joined_at=int(time.time()),
            )
            db.add(member)
            going = True

        # Keep current_size accurate
        member_count = db.query(WebLFGMember).filter_by(group_id=group.id).count()
        if not going:
            member_count -= 1  # we just deleted but haven't flushed yet
        group.current_size = max(0, member_count)
        group.updated_at = int(time.time())

        db.commit()

        # Return updated going list
        members = db.query(WebLFGMember).filter_by(group_id=group.id).all()
        going_users = []
        for m in members:
            u = db.query(WebUser).filter_by(id=m.user_id).first()
            if u:
                going_users.append({
                    'display_name': u.display_name or u.username,
                    'avatar_url': u.avatar_url,
                })

    return JsonResponse({
        'going': going,
        'going_count': len(going_users),
        'going_users': going_users,
    })


@require_GET
def api_ffxiv_ocean_fishing_schedule(request):
    """Return next N ocean fishing windows as JSON (for bots/webhooks)."""
    count = min(int(request.GET.get('count', 5)), 20)
    schedule = _build_schedule(count)
    return JsonResponse({
        'windows': [
            {
                'window_num':   w['window_num'],
                'departure_ts': w['departure_ts'],
                'departure_iso': datetime.fromtimestamp(w['departure_ts'], tz=timezone.utc).isoformat(),
                'reg_opens_ts': w['reg_opens_ts'],
                'route':        w['route']['name'],
                'stops':        w['route']['stops'],
                'times':        w['route']['times'],
                'blue_fish':    w['route']['blue_fish'],
                'achievement_fish': [f['name'] for f in w['route']['achievement_fish']],
                'is_active':    w['is_active'],
            }
            for w in schedule
        ]
    })


# ---------------------------------------------------------------------------
# FFXIV Achievement -> XP/Legacy reward map
# key = unique string we store in web_ffxiv_achievement_rewards
# xp_action / legacy_action = keys into XP_ACTIONS / LEGACY_ACTIONS
# detect = function(char_data) -> bool
# ---------------------------------------------------------------------------

FFXIV_ACHIEVEMENT_REWARDS = [
    # --- Character link (one-time) ---
    {
        'key': 'char_linked',
        'name': 'FFXIV Character Linked',
        'xp_action': 'ffxiv_char_linked',
        'legacy_action': 'ffxiv_char_linked',
        'on_link': True,  # awarded at link time, not from Lodestone data
    },
    # --- Collection milestones (from mount_count / minion_count) ---
    {'key': 'mount_50',  'name': '50 Mounts Collected',  'xp_action': 'ffxiv_mount_50',  'legacy_action': None,             'mount_threshold': 50},
    {'key': 'mount_100', 'name': '100 Mounts Collected', 'xp_action': 'ffxiv_mount_100', 'legacy_action': 'ffxiv_mount_100','mount_threshold': 100},
    {'key': 'mount_200', 'name': '200 Mounts Collected', 'xp_action': 'ffxiv_mount_200', 'legacy_action': 'ffxiv_mount_200','mount_threshold': 200},
    {'key': 'mount_300', 'name': '300 Mounts Collected', 'xp_action': 'ffxiv_mount_300', 'legacy_action': 'ffxiv_mount_300','mount_threshold': 300},
    {'key': 'minion_50',  'name': '50 Minions Collected',  'xp_action': 'ffxiv_minion_50',  'legacy_action': None,              'minion_threshold': 50},
    {'key': 'minion_100', 'name': '100 Minions Collected', 'xp_action': 'ffxiv_minion_100', 'legacy_action': None,              'minion_threshold': 100},
]

# Achievement IDs from Lodestone that map to our reward keys
# These are the Lodestone achievement page IDs (checked against title/category)
FFXIV_LODESTONE_ACHIEVEMENT_MAP = {
    # Mentor status - The Mentor achievement category
    'mentor_complete':         {'key': 'ffxiv_mentor',           'xp': 'ffxiv_mentor',            'leg': 'ffxiv_mentor',            'name': 'Mentor Crown Earned'},
    # Commendations
    'commendations_50':        {'key': 'ffxiv_comm_50',          'xp': 'ffxiv_commendations_50',   'leg': None,                      'name': '50 Commendations'},
    'commendations_500':       {'key': 'ffxiv_comm_500',         'xp': 'ffxiv_commendations_500',  'leg': 'ffxiv_commendations_500', 'name': '500 Commendations'},
    # Ultimate clears (by achievement name pattern)
    'ultimate_clear':          {'key': 'ffxiv_ultimate',         'xp': 'ffxiv_ultimate_clear',     'leg': 'ffxiv_ultimate_clear',    'name': 'Ultimate Raid Cleared'},
    'savage_clear':            {'key': 'ffxiv_savage',           'xp': 'ffxiv_savage_clear',       'leg': 'ffxiv_savage_clear',      'name': 'Savage Raid Cleared'},
    # All jobs at cap
    'all_jobs_cap':            {'key': 'ffxiv_all_jobs',         'xp': 'ffxiv_all_jobs_cap',       'leg': 'ffxiv_all_jobs_cap',      'name': 'All Jobs at Level Cap'},
    # Blue Mage
    'blue_mage_all':           {'key': 'ffxiv_blumage_all',      'xp': 'ffxiv_blue_mage_all',      'leg': 'ffxiv_blue_mage_all',     'name': 'All Blue Mage Spells'},
    # Triple Triad
    'triple_triad_all':        {'key': 'ffxiv_tt_all',           'xp': 'ffxiv_triple_triad_all',   'leg': 'ffxiv_triple_triad_all',  'name': 'All Triple Triad Cards'},
    # Deep Dungeon floor 200
    'deep_dungeon_200':        {'key': 'ffxiv_dd200',            'xp': 'ffxiv_deep_dungeon_200',   'leg': 'ffxiv_deep_dungeon_200',  'name': 'Floor 200 of Deep Dungeon'},
    # Ocean fishing achievement
    'ocean_fishing_ach':       {'key': 'ffxiv_oceanfishing',     'xp': 'ffxiv_ocean_fishing_ach',  'leg': None,                      'name': 'Ocean Fishing Achievement'},
    # Big fish
    'big_fish':                {'key': 'ffxiv_bigfish',          'xp': 'ffxiv_big_fish',           'leg': None,                      'name': 'Big Fish Caught'},
}


# ---------------------------------------------------------------------------
# Lodestone scraper helpers
# ---------------------------------------------------------------------------

def _lodestone_search_characters(name, world=None):
    """Search Lodestone for characters by name (+optional world). Returns list of dicts."""
    try:
        from bs4 import BeautifulSoup
        params = {'q': name}
        if world:
            params['worldname'] = world
        url = f'{_LODESTONE_BASE}/character/'
        resp = requests.get(url, params=params, headers=_LODESTONE_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')
        results = []
        for entry in soup.select('.entry')[:10]:
            name_el = entry.select_one('.entry__name')
            world_el = entry.select_one('.entry__world')
            avatar_el = entry.select_one('.entry__chara__face img')
            link_el = entry.select_one('a.entry__link')
            if not name_el or not link_el:
                continue
            href = link_el.get('href', '')
            lid_match = re.search(r'/character/(\d+)/', href)
            if not lid_match:
                continue
            results.append({
                'lodestone_id': lid_match.group(1),
                'name': name_el.get_text(strip=True),
                'world': world_el.get_text(strip=True).replace('\xa0', ' ') if world_el else '',
                'avatar_url': avatar_el.get('src', '') if avatar_el else '',
            })
        return results
    except Exception as e:
        logger.warning(f'Lodestone search failed: {e}')
        return []


def _lodestone_fetch_character(lodestone_id):
    """Fetch full character profile from Lodestone. Returns dict or None."""
    try:
        from bs4 import BeautifulSoup
        url = f'{_LODESTONE_BASE}/character/{lodestone_id}/'
        resp = requests.get(url, headers=_LODESTONE_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')

        name_el    = soup.select_one('.frame__chara__name')
        world_el   = soup.select_one('.frame__chara__world')
        title_el   = soup.select_one('.frame__chara__title')
        avatar_el  = soup.select_one('.frame__chara__face img')
        portrait_el = soup.select_one('.character__detail__image img')
        fc_el      = soup.select_one('.character__freecompany__name h4')
        fc_tag_el  = soup.select_one('.character__freecompany__name .entry__freecompany__tag')

        # Active class/job - the current equipped job icon
        job_el = soup.select_one('.character__class__data .character__class_icon img')
        active_job = None
        if job_el:
            alt = job_el.get('alt', '')
            if alt:
                active_job = alt

        world_raw = world_el.get_text(strip=True) if world_el else ''
        # Format: "WorldName\xa0(DatacenterName)" or "WorldName (Datacenter)"
        world_parts = re.split(r'\s*[\[\(]', world_raw.replace('\xa0', ' '))
        world_name = world_parts[0].strip() if world_parts else world_raw
        datacenter = world_parts[1].rstrip('])').strip() if len(world_parts) > 1 else ''

        return {
            'lodestone_id': str(lodestone_id),
            'character_name': name_el.get_text(strip=True) if name_el else '',
            'world': world_name,
            'datacenter': datacenter,
            'title': title_el.get_text(strip=True) if title_el else None,
            'avatar_url': avatar_el.get('src', '') if avatar_el else '',
            'portrait_url': portrait_el.get('src', '') if portrait_el else '',
            'free_company': fc_el.get_text(strip=True) if fc_el else None,
            'fc_tag': fc_tag_el.get_text(strip=True) if fc_tag_el else None,
            'active_job': active_job,
        }
    except Exception as e:
        logger.warning(f'Lodestone character fetch failed for {lodestone_id}: {e}')
        return None


def _lodestone_fetch_mounts(lodestone_id):
    """
    Fetch mount list from Lodestone.
    Lodestone renders mount names via async tooltip URLs, not inline HTML.
    We extract the icon image src (filename hash) as a stable identifier,
    then resolve names against the XIVAPI catalog by icon path.
    Returns list of icon-hash strings, or None if profile is private.
    """
    try:
        from bs4 import BeautifulSoup
        url = f'{_LODESTONE_BASE}/character/{lodestone_id}/mount/'
        resp = requests.get(url, headers=_LODESTONE_HEADERS, timeout=15)
        if resp.status_code == 403:
            return None  # private profile
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Store tooltip_hash (from data-tooltip_href) as stable identifier for name resolution.
        # Format: /lodestone/character/{id}/mount/tooltip/{HASH}
        hashes = []
        for li in soup.select('li.mount__list_icon'):
            href = li.get('data-tooltip_href', '')
            tip_hash = href.split('/')[-1] if href else ''
            if tip_hash:
                hashes.append(tip_hash)
        return hashes
    except Exception as e:
        logger.warning(f'Lodestone mount fetch failed for {lodestone_id}: {e}')
        return []


def _lodestone_fetch_minions(lodestone_id):
    """
    Fetch minion list from Lodestone. Stores tooltip hashes for name resolution.
    Returns list of tooltip-hash strings, or None if profile is private.
    """
    try:
        from bs4 import BeautifulSoup
        url = f'{_LODESTONE_BASE}/character/{lodestone_id}/minion/'
        resp = requests.get(url, headers=_LODESTONE_HEADERS, timeout=15)
        if resp.status_code == 403:
            return None  # private profile
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')
        hashes = []
        for li in soup.select('li.minion__list_icon'):
            href = li.get('data-tooltip_href', '')
            tip_hash = href.split('/')[-1] if href else ''
            if tip_hash:
                hashes.append(tip_hash)
        return hashes
    except Exception as e:
        logger.warning(f'Lodestone minion fetch failed for {lodestone_id}: {e}')
        return []


_JOB_ROLES = {
    # Tank
    'Paladin': 'Tank', 'Warrior': 'Tank', 'Dark Knight': 'Tank', 'Gunbreaker': 'Tank',
    # Healer
    'White Mage': 'Healer', 'Scholar': 'Healer', 'Astrologian': 'Healer', 'Sage': 'Healer',
    # Melee DPS
    'Monk': 'Melee DPS', 'Dragoon': 'Melee DPS', 'Ninja': 'Melee DPS',
    'Samurai': 'Melee DPS', 'Reaper': 'Melee DPS', 'Viper': 'Melee DPS',
    # Physical Ranged DPS
    'Bard': 'Physical Ranged DPS', 'Machinist': 'Physical Ranged DPS', 'Dancer': 'Physical Ranged DPS',
    # Magical Ranged DPS
    'Black Mage': 'Magical Ranged DPS', 'Summoner': 'Magical Ranged DPS',
    'Red Mage': 'Magical Ranged DPS', 'Blue Mage': 'Magical Ranged DPS',
    'Pictomancer': 'Magical Ranged DPS',
    # Crafter
    'Carpenter': 'Crafter', 'Blacksmith': 'Crafter', 'Armorer': 'Crafter',
    'Goldsmith': 'Crafter', 'Leatherworker': 'Crafter', 'Weaver': 'Crafter',
    'Alchemist': 'Crafter', 'Culinarian': 'Crafter',
    # Gatherer
    'Miner': 'Gatherer', 'Botanist': 'Gatherer', 'Fisher': 'Gatherer',
}

_ROLE_ORDER = ['Tank', 'Healer', 'Melee DPS', 'Physical Ranged DPS', 'Magical Ranged DPS', 'Crafter', 'Gatherer']


def _lodestone_fetch_class_jobs(lodestone_id):
    """
    Fetch class/job levels from Lodestone character class_job page.
    Returns list of job dicts or None if profile is private/unreachable.
    Each dict: {name, level, xp_current, xp_max, icon_url, role}
    Unleveled jobs (level "-") are included with level=0.
    """
    try:
        from bs4 import BeautifulSoup
        url = f'{_LODESTONE_BASE}/character/{lodestone_id}/class_job/'
        resp = requests.get(url, headers=_LODESTONE_HEADERS, timeout=15)
        if resp.status_code == 403:
            return None
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, 'html.parser')
        jobs = []

        for li in soup.select('ul.character__job li'):
            level_el = li.select_one('.character__job__level')
            name_el  = li.select_one('.character__job__name')
            exp_el   = li.select_one('.character__job__exp')
            icon_el  = li.select_one('.character__job__icon img')

            if not name_el:
                continue

            # Job name is the visible text; tooltip has "Job / Class" format
            name = name_el.get_text(strip=True)
            if not name:
                continue

            level_text = level_el.get_text(strip=True) if level_el else '-'
            level = 0 if level_text == '-' else int(level_text) if level_text.isdigit() else 0

            # XP: "4,842,575 / 6,171,000" or "- / -"
            xp_current = 0
            xp_max = 0
            if exp_el:
                xp_text = exp_el.get_text(strip=True).replace(',', '')
                parts = [p.strip() for p in xp_text.split('/')]
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    xp_current = int(parts[0])
                    xp_max = int(parts[1])

            icon_url = icon_el.get('src', '') if icon_el else ''

            jobs.append({
                'name': name,
                'level': level,
                'xp_current': xp_current,
                'xp_max': xp_max,
                'icon_url': icon_url,
                'role': _JOB_ROLES.get(name, 'Other'),
            })

        return jobs
    except Exception as e:
        logger.warning(f'Lodestone class_job fetch failed for {lodestone_id}: {e}')
        return []


def _resolve_item_names(lodestone_id, tooltip_hashes, item_type, db):
    """
    Resolve a list of tooltip hashes to names. Checks DB cache first;
    fetches uncached ones from Lodestone tooltip URLs (rate-limited to 1/s).
    Returns dict {hash: name}.
    """
    from app.questlog_web.models import WebFfxivItemName
    from bs4 import BeautifulSoup

    if not tooltip_hashes:
        return {}

    # Load cached names from DB
    cached = db.query(WebFfxivItemName).filter(
        WebFfxivItemName.tooltip_hash.in_(tooltip_hashes)
    ).all()
    name_map = {r.tooltip_hash: r.item_name for r in cached}

    # Fetch uncached ones
    uncached = [h for h in tooltip_hashes if h not in name_map]
    if item_type == 'mount':
        base_url = f'{_LODESTONE_BASE}/character/{lodestone_id}/mount/tooltip/'
    else:
        base_url = f'{_LODESTONE_BASE}/character/{lodestone_id}/minion/tooltip/'

    for tip_hash in uncached:
        try:
            import time as _time
            resp = requests.get(base_url + tip_hash, headers=_LODESTONE_HEADERS, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                label = soup.select_one('h4.mount__header__label') or soup.select_one('h4.minion__header__label')
                if label:
                    name = label.get_text(strip=True)
                    name_map[tip_hash] = name
                    record = WebFfxivItemName(
                        tooltip_hash=tip_hash,
                        item_type=item_type,
                        item_name=name,
                        lodestone_url=base_url + tip_hash,
                        created_at=int(_time.time()),
                    )
                    db.add(record)
            _time.sleep(0.3)  # be polite to Lodestone
        except Exception as e:
            logger.warning(f'Tooltip fetch failed for {tip_hash}: {e}')
            name_map[tip_hash] = tip_hash[:8] + '...'

    try:
        db.flush()
    except Exception:
        pass

    return name_map


def _lodestone_fetch_mount_count(lodestone_id):
    """Quick count-only fetch - avoids full parse. Returns int or None if private."""
    try:
        from bs4 import BeautifulSoup
        url = f'{_LODESTONE_BASE}/character/{lodestone_id}/mount/'
        resp = requests.get(url, headers=_LODESTONE_HEADERS, timeout=15)
        if resp.status_code == 403:
            return None
        if resp.status_code != 200:
            return 0
        soup = BeautifulSoup(resp.text, 'html.parser')
        return len(soup.select('li.mount__list_icon'))
    except Exception:
        return 0


_ACHIEVEMENT_CATEGORIES = [
    (1,  'General'),
    (2,  'Dungeons'),
    (3,  'Trials'),
    (4,  'Raids'),
    (5,  'The Hunt'),
    (6,  'Treasure Hunt'),
    (71, 'Field Operations'),
]

def _lodestone_fetch_achievements(lodestone_id):
    """Scrape all achievement categories from Lodestone.
    Returns dict: {category_name: [{id, name, icon, pts, completed}]}
    Returns None if profile is private/forbidden."""
    try:
        from bs4 import BeautifulSoup
        import re as _re
        result = {}
        for cat_id, cat_name in _ACHIEVEMENT_CATEGORIES:
            url = f'{_LODESTONE_BASE}/character/{lodestone_id}/achievement/category/{cat_id}/'
            resp = requests.get(url, headers=_LODESTONE_HEADERS, timeout=15)
            if resp.status_code == 403:
                return None
            if resp.status_code != 200:
                result[cat_name] = []
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            items = []
            for a in soup.select('a.entry__achievement'):
                href = a.get('href', '')
                m = _re.search(r'/achievement/detail/(\d+)/', href)
                ach_id = int(m.group(1)) if m else None
                name_el = a.select_one('.entry__activity__txt')
                name = name_el.text.strip() if name_el else ''
                icon_el = a.select_one('img')
                icon = icon_el.get('src', '') if icon_el else ''
                pts_el = a.select_one('.entry__achievement__number')
                pts = int(pts_el.text.strip()) if pts_el else 0
                completed = 'entry__achievement--complete' in a.get('class', [])
                if name:
                    items.append({'id': ach_id, 'name': name, 'icon': icon, 'pts': pts, 'completed': completed})
            result[cat_name] = items
        return result
    except Exception as e:
        logger.warning(f'Lodestone achievement fetch failed for {lodestone_id}: {e}')
        return {}


def _ffxiv_collect_catalog(endpoint, url_slug, limit=2000):
    """Generic FFXIV Collect catalog fetcher. Returns list of enriched item dicts."""
    try:
        resp = requests.get(
            f'{_FFXIV_COLLECT_BASE}/{endpoint}',
            params={'limit': limit},
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        def _name(v):
            """Extract string name from either a string or a {id, name} dict."""
            if isinstance(v, dict):
                return v.get('name', '')
            return v or ''

        results = resp.json().get('results', [])
        out = []
        for r in results:
            if not r.get('name'):
                continue
            out.append({
                'id': r['id'],
                'name': r['name'],
                'icon': r.get('icon', ''),
                'image': r.get('image', r.get('icon', '')),
                'owned_pct': r.get('owned', ''),
                'url': f'https://ffxivcollect.com/{url_slug}/{r["id"]}',
                'sources': r.get('sources', []),
                'patch': r.get('patch', ''),
                'command': r.get('command', ''),
                'category': _name(r.get('category', '')),
                'aspect': _name(r.get('aspect', '')),
                'rank': r.get('rank', ''),
                'rarity': r.get('rarity', ''),
                'type': _name(r.get('type', '')),
            })
        return out
    except Exception as e:
        logger.warning(f'FFXIV Collect {endpoint} catalog failed: {e}')
        return []


def _ffxiv_collect_mounts():
    return _ffxiv_collect_catalog('mounts', 'mounts')


def _ffxiv_collect_minions():
    return _ffxiv_collect_catalog('minions', 'minions')


def _ffxiv_collect_character(lodestone_id):
    """Fetch character summary from FFXIV Collect. Returns dict with collection counts or None."""
    try:
        resp = requests.get(
            f'{_FFXIV_COLLECT_BASE}/characters/{lodestone_id}',
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        logger.warning(f'FFXIV Collect character fetch failed: {e}')
        return None


def _process_collection_rewards(db, user_id, char, old_mount_count, old_minion_count):
    """Check collection milestones and award XP/Legacy for newly crossed thresholds."""
    thresholds = [
        (50,  'mount_50',  'ffxiv_mount_50',  None),
        (100, 'mount_100', 'ffxiv_mount_100', 'ffxiv_mount_100'),
        (200, 'mount_200', 'ffxiv_mount_200', 'ffxiv_mount_200'),
        (300, 'mount_300', 'ffxiv_mount_300', 'ffxiv_mount_300'),
    ]
    rewards_given = []
    for threshold, key, xp_action, leg_action in thresholds:
        if char.mount_count >= threshold and old_mount_count < threshold:
            existing = db.query(WebFfxivAchievementReward).filter_by(
                user_id=user_id, achievement_key=key
            ).first()
            if not existing:
                xp_r = award_xp(user_id, xp_action, source='ffxiv', ref_id=char.lodestone_id)
                leg_r = award_legacy(user_id, leg_action, source='ffxiv', ref_id=char.lodestone_id) if leg_action else 0
                db.add(WebFfxivAchievementReward(
                    user_id=user_id,
                    lodestone_id=char.lodestone_id,
                    achievement_key=key,
                    achievement_name=f'{threshold} Mounts Collected',
                    xp_awarded=xp_r or 0,
                    legacy_awarded=leg_r or 0,
                    awarded_at=int(time.time()),
                ))
                rewards_given.append({'name': f'{threshold} Mounts Collected', 'xp': xp_r, 'legacy': leg_r})

    minion_thresholds = [
        (50,  'minion_50',  'ffxiv_minion_50',  None),
        (100, 'minion_100', 'ffxiv_minion_100', None),
    ]
    for threshold, key, xp_action, leg_action in minion_thresholds:
        if char.minion_count >= threshold and old_minion_count < threshold:
            existing = db.query(WebFfxivAchievementReward).filter_by(
                user_id=user_id, achievement_key=key
            ).first()
            if not existing:
                xp_r = award_xp(user_id, xp_action, source='ffxiv', ref_id=char.lodestone_id)
                db.add(WebFfxivAchievementReward(
                    user_id=user_id,
                    lodestone_id=char.lodestone_id,
                    achievement_key=key,
                    achievement_name=f'{threshold} Minions Collected',
                    xp_awarded=xp_r or 0,
                    legacy_awarded=0,
                    awarded_at=int(time.time()),
                ))
                rewards_given.append({'name': f'{threshold} Minions Collected', 'xp': xp_r, 'legacy': 0})
    return rewards_given


def _process_job_rewards(db, user_id, char, jobs):
    """Award XP/Legacy for job level milestones. One-time per job/threshold."""
    rewards_given = []
    if not jobs:
        return rewards_given

    # Per-job: first job to hit level cap (90/100 depending on expansion)
    # Level cap = highest level among all combat jobs (Shadowbringers=80, Endwalker=90, Dawntrail=100)
    combat_roles = {'Tank', 'Healer', 'Melee DPS', 'Physical Ranged DPS', 'Magical Ranged DPS'}
    combat_jobs = [j for j in jobs if j.get('role') in combat_roles]
    craft_jobs  = [j for j in jobs if j.get('role') == 'Crafter']
    gather_jobs = [j for j in jobs if j.get('role') == 'Gatherer']

    level_cap = max((j['level'] for j in combat_jobs), default=0) if combat_jobs else 0
    if level_cap < 80:
        level_cap = 90  # assume Endwalker cap if we have no data yet

    for job in combat_jobs:
        if job['level'] < level_cap:
            continue
        key = f'job_cap_{job["name"].lower().replace(" ", "_")}'
        existing = db.query(WebFfxivAchievementReward).filter_by(
            user_id=user_id, achievement_key=key
        ).first()
        if not existing:
            xp_r = award_xp(user_id, 'ffxiv_job_level_cap', source='ffxiv', ref_id=f'{char.lodestone_id}_{key}')
            db.add(WebFfxivAchievementReward(
                user_id=user_id,
                lodestone_id=char.lodestone_id,
                achievement_key=key,
                achievement_name=f'{job["name"]} Level Cap',
                xp_awarded=xp_r or 0,
                legacy_awarded=0,
                awarded_at=int(time.time()),
            ))
            rewards_given.append({'name': f'{job["name"]} Level Cap', 'xp': xp_r, 'legacy': 0})

    # All combat jobs at cap
    if combat_jobs and all(j['level'] >= level_cap for j in combat_jobs):
        key = 'all_combat_jobs_cap'
        existing = db.query(WebFfxivAchievementReward).filter_by(
            user_id=user_id, achievement_key=key
        ).first()
        if not existing:
            xp_r = award_xp(user_id, 'ffxiv_all_jobs_cap', source='ffxiv', ref_id=char.lodestone_id)
            leg_r = award_legacy(user_id, 'ffxiv_all_jobs_cap', source='ffxiv', ref_id=char.lodestone_id)
            db.add(WebFfxivAchievementReward(
                user_id=user_id,
                lodestone_id=char.lodestone_id,
                achievement_key=key,
                achievement_name='All Combat Jobs at Level Cap',
                xp_awarded=xp_r or 0,
                legacy_awarded=leg_r or 0,
                awarded_at=int(time.time()),
            ))
            rewards_given.append({'name': 'All Combat Jobs at Level Cap', 'xp': xp_r, 'legacy': leg_r})

    # Any crafter at cap
    crafter_cap = max((j['level'] for j in craft_jobs), default=0) if craft_jobs else 0
    if crafter_cap >= 90:
        for job in craft_jobs:
            if job['level'] < crafter_cap:
                continue
            key = f'crafter_cap_{job["name"].lower()}'
            existing = db.query(WebFfxivAchievementReward).filter_by(
                user_id=user_id, achievement_key=key
            ).first()
            if not existing:
                xp_r = award_xp(user_id, 'ffxiv_crafter_cap', source='ffxiv', ref_id=f'{char.lodestone_id}_{key}')
                db.add(WebFfxivAchievementReward(
                    user_id=user_id,
                    lodestone_id=char.lodestone_id,
                    achievement_key=key,
                    achievement_name=f'{job["name"]} Level Cap',
                    xp_awarded=xp_r or 0,
                    legacy_awarded=0,
                    awarded_at=int(time.time()),
                ))
                rewards_given.append({'name': f'{job["name"]} Level Cap', 'xp': xp_r, 'legacy': 0})

    # All crafters at cap
    if craft_jobs and crafter_cap >= 90 and all(j['level'] >= crafter_cap for j in craft_jobs):
        key = 'all_crafters_cap'
        existing = db.query(WebFfxivAchievementReward).filter_by(
            user_id=user_id, achievement_key=key
        ).first()
        if not existing:
            xp_r = award_xp(user_id, 'ffxiv_all_crafters_cap', source='ffxiv', ref_id=char.lodestone_id)
            leg_r = award_legacy(user_id, 'ffxiv_all_crafters_cap', source='ffxiv', ref_id=char.lodestone_id)
            db.add(WebFfxivAchievementReward(
                user_id=user_id,
                lodestone_id=char.lodestone_id,
                achievement_key=key,
                achievement_name='All Crafters at Level Cap',
                xp_awarded=xp_r or 0,
                legacy_awarded=leg_r or 0,
                awarded_at=int(time.time()),
            ))
            rewards_given.append({'name': 'All Crafters at Level Cap', 'xp': xp_r, 'legacy': leg_r})

    # Any gatherer at cap
    gatherer_cap = max((j['level'] for j in gather_jobs), default=0) if gather_jobs else 0
    if gatherer_cap >= 90:
        for job in gather_jobs:
            if job['level'] < gatherer_cap:
                continue
            key = f'gatherer_cap_{job["name"].lower()}'
            existing = db.query(WebFfxivAchievementReward).filter_by(
                user_id=user_id, achievement_key=key
            ).first()
            if not existing:
                xp_r = award_xp(user_id, 'ffxiv_gatherer_cap', source='ffxiv', ref_id=f'{char.lodestone_id}_{key}')
                db.add(WebFfxivAchievementReward(
                    user_id=user_id,
                    lodestone_id=char.lodestone_id,
                    achievement_key=key,
                    achievement_name=f'{job["name"]} Level Cap',
                    xp_awarded=xp_r or 0,
                    legacy_awarded=0,
                    awarded_at=int(time.time()),
                ))
                rewards_given.append({'name': f'{job["name"]} Level Cap', 'xp': xp_r, 'legacy': 0})

    return rewards_given


# ---------------------------------------------------------------------------
# Character Linking Views
# ---------------------------------------------------------------------------

@require_GET
@web_login_required
def api_ffxiv_search_characters(request):
    """Search Lodestone for characters by name/world."""
    name = request.GET.get('name', '').strip()
    world = request.GET.get('world', '').strip()
    if len(name) < 2:
        return JsonResponse({'error': 'Name too short'}, status=400)
    results = _lodestone_search_characters(name, world or None)
    return JsonResponse({'results': results})


@require_POST
@web_login_required
def api_ffxiv_link_character(request):
    """Link a Lodestone character to the logged-in user account."""
    web_user_id = request.session.get('web_user_id')
    try:
        data = json.loads(request.body)
        lodestone_id = str(data.get('lodestone_id', '')).strip()
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request'}, status=400)

    if not re.match(r'^\d{1,20}$', lodestone_id):
        return JsonResponse({'error': 'Invalid Lodestone ID'}, status=400)

    # Fetch character from Lodestone to verify it exists
    char_data = _lodestone_fetch_character(lodestone_id)
    if not char_data or not char_data.get('character_name'):
        return JsonResponse({'error': 'Could not find that character on Lodestone. Try again in a moment.'}, status=404)

    now = int(time.time())
    with get_db_session() as db:
        # Check if already linked by this user
        existing = db.query(WebFfxivCharacter).filter_by(
            user_id=web_user_id, lodestone_id=lodestone_id
        ).first()
        if existing:
            return JsonResponse({'error': 'You already have this character linked.'}, status=409)

        # If user has another primary, demote it
        db.query(WebFfxivCharacter).filter_by(
            user_id=web_user_id, is_primary=True
        ).update({'is_primary': False})

        char = WebFfxivCharacter(
            user_id=web_user_id,
            lodestone_id=lodestone_id,
            character_name=char_data['character_name'],
            world=char_data['world'],
            datacenter=char_data['datacenter'],
            avatar_url=char_data.get('avatar_url', ''),
            portrait_url=char_data.get('portrait_url', ''),
            title=char_data.get('title'),
            free_company=char_data.get('free_company'),
            fc_tag=char_data.get('fc_tag'),
            active_job=char_data.get('active_job'),
            is_primary=True,
            sync_status='pending',
            created_at=now,
            updated_at=now,
        )
        db.add(char)
        db.flush()

        # Award one-time XP + Legacy for linking
        already_awarded = db.query(WebFfxivAchievementReward).filter_by(
            user_id=web_user_id, achievement_key='char_linked'
        ).first()
        if not already_awarded:
            xp_r = award_xp(web_user_id, 'ffxiv_char_linked', source='ffxiv', ref_id=lodestone_id)
            leg_r = award_legacy(web_user_id, 'ffxiv_char_linked', source='ffxiv', ref_id=lodestone_id)
            db.add(WebFfxivAchievementReward(
                user_id=web_user_id,
                lodestone_id=lodestone_id,
                achievement_key='char_linked',
                achievement_name='FFXIV Character Linked',
                xp_awarded=xp_r or 0,
                legacy_awarded=leg_r or 0,
                awarded_at=now,
            ))

        db.commit()

    return JsonResponse({
        'ok': True,
        'character': {
            'name': char_data['character_name'],
            'world': char_data['world'],
            'datacenter': char_data['datacenter'],
            'avatar_url': char_data.get('avatar_url', ''),
            'lodestone_id': lodestone_id,
        },
    })


@require_POST
@web_login_required
def api_ffxiv_sync_character(request):
    """Trigger a Lodestone sync for the user's primary character."""
    web_user_id = request.session.get('web_user_id')
    try:
        data = json.loads(request.body)
        lodestone_id = str(data.get('lodestone_id', '')).strip()
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid request'}, status=400)

    with get_db_session() as db:
        char = db.query(WebFfxivCharacter).filter_by(
            user_id=web_user_id, lodestone_id=lodestone_id
        ).first()
        if not char:
            return JsonResponse({'error': 'Character not found'}, status=404)

        # Rate limit: don't sync more than once per 5 minutes
        if char.last_synced_at and int(time.time()) - char.last_synced_at < 300:
            wait = 300 - (int(time.time()) - char.last_synced_at)
            mins = max(1, round(wait / 60))
            return JsonResponse({'error': f'Sync is on cooldown - try again in {mins} minute{"s" if mins != 1 else ""}.'}, status=200)

        char.sync_status = 'syncing'
        db.commit()

        old_mount_count = char.mount_count or 0
        old_minion_count = char.minion_count or 0

        # Fetch mounts
        mounts = _lodestone_fetch_mounts(lodestone_id)
        if mounts is None:
            char.sync_status = 'private'
            char.sync_error = 'Mount/minion collection is set to private on Lodestone.'
            char.last_synced_at = int(time.time())
            char.updated_at = int(time.time())
            db.commit()
            return JsonResponse({'error': char.sync_error, 'status': 'private'}, status=200)

        # Fetch minions
        minions = _lodestone_fetch_minions(lodestone_id)
        if minions is None:
            minions = []

        # Fetch class/job levels
        jobs = _lodestone_fetch_class_jobs(lodestone_id) or []

        # Fetch achievements (all categories) - runs in background to avoid slow sync
        import threading as _threading
        def _bg_achievements():
            try:
                ach = _lodestone_fetch_achievements(lodestone_id)
                if ach is not None:
                    with get_db_session() as bg_db:
                        bg_char = bg_db.query(WebFfxivCharacter).filter_by(
                            user_id=web_user_id, lodestone_id=lodestone_id
                        ).first()
                        if bg_char:
                            bg_char.achievements_json = json.dumps(ach)
                            bg_db.commit()
            except Exception as e:
                logger.warning(f'Background achievement sync failed: {e}')
        _threading.Thread(target=_bg_achievements, daemon=True).start()

        # Update character data from Lodestone profile too
        char_data = _lodestone_fetch_character(lodestone_id)
        if char_data:
            char.character_name = char_data['character_name']
            char.world = char_data['world']
            char.datacenter = char_data['datacenter']
            char.avatar_url = char_data.get('avatar_url', char.avatar_url)
            char.portrait_url = char_data.get('portrait_url', char.portrait_url)
            char.title = char_data.get('title', char.title)
            char.free_company = char_data.get('free_company', char.free_company)
            char.fc_tag = char_data.get('fc_tag', char.fc_tag)
            char.active_job = char_data.get('active_job', char.active_job)

        # Resolve tooltip hashes to names: use DB cache for known ones, spawn thread for unknowns
        from app.questlog_web.models import WebFfxivItemName as _ItemName
        all_hashes = mounts + minions
        cached_rows = db.query(_ItemName).filter(_ItemName.tooltip_hash.in_(all_hashes)).all()
        cached_map = {r.tooltip_hash: r.item_name for r in cached_rows}

        mount_names = [cached_map.get(h, h) for h in mounts]
        minion_names = [cached_map.get(h, h) for h in minions]
        needs_resolution = [h for h in all_hashes if h not in cached_map]

        char.mounts_json = json.dumps(mount_names)
        char.minions_json = json.dumps(minion_names)
        char.jobs_json = json.dumps(jobs)
        char.mount_count = len(mounts)
        char.minion_count = len(minions)
        char.sync_status = 'ok' if not needs_resolution else 'resolving'
        char.sync_error = None
        char.last_synced_at = int(time.time())
        char.updated_at = int(time.time())

        # Check and award collection milestones (mounts/minions + job milestones)
        rewards = _process_collection_rewards(db, web_user_id, char, old_mount_count, old_minion_count)
        rewards += _process_job_rewards(db, web_user_id, char, jobs)
        db.commit()

        # Resolve unknown names in background thread (won't block response)
        if needs_resolution:
            import threading
            char_id = char.id

            def _bg_resolve():
                try:
                    with get_db_session() as bg_db:
                        mount_unknowns = [h for h in mounts if h in needs_resolution]
                        minion_unknowns = [h for h in minions if h in needs_resolution]
                        mount_map = _resolve_item_names(lodestone_id, mount_unknowns, 'mount', bg_db)
                        minion_map = _resolve_item_names(lodestone_id, minion_unknowns, 'minion', bg_db)
                        full_map = {**cached_map, **mount_map, **minion_map}
                        bg_char = bg_db.query(WebFfxivCharacter).filter_by(id=char_id).first()
                        if bg_char:
                            bg_char.mounts_json = json.dumps([full_map.get(h, h) for h in mounts])
                            bg_char.minions_json = json.dumps([full_map.get(h, h) for h in minions])
                            if bg_char.sync_status == 'resolving':
                                bg_char.sync_status = 'ok'
                        bg_db.commit()
                except Exception as e:
                    logger.warning(f'Background name resolution failed: {e}')

            threading.Thread(target=_bg_resolve, daemon=True).start()

    return JsonResponse({
        'ok': True,
        'mount_count': len(mounts),
        'minion_count': len(minions),
        'job_count': len(jobs),
        'rewards': rewards,
        'last_synced_at': char.last_synced_at,
        'resolving': bool(needs_resolution),
    })


@require_GET
@web_login_required
def api_ffxiv_achievements_ready(request):
    """Poll endpoint: returns {ready: true} once achievements_json is populated after sync."""
    web_user_id = request.session.get('web_user_id')
    lodestone_id = request.GET.get('lodestone_id', '').strip()
    if not lodestone_id:
        return JsonResponse({'ready': False})
    with get_db_session() as db:
        char = db.query(WebFfxivCharacter).filter_by(
            user_id=web_user_id, lodestone_id=lodestone_id
        ).first()
        ready = bool(char and char.achievements_json)
    return JsonResponse({'ready': ready})


# ---------------------------------------------------------------------------
# Collection Tracker View
# ---------------------------------------------------------------------------

@add_web_user_context
@web_login_required
def ffxiv_collection(request):
    """Mount/minion/achievement collection tracker."""
    web_user = get_web_user(request)
    web_user_id = request.session.get('web_user_id')

    character = None
    mounts_owned = []
    minions_owned = []
    jobs_by_role = []
    rewards_earned = []
    achievements_by_cat = {}  # {cat_name: [{id, name, icon, pts, completed}]}

    with get_db_session() as db:
        character = db.query(WebFfxivCharacter).filter_by(
            user_id=web_user_id, is_primary=True
        ).first()

        if character:
            if character.mounts_json:
                try:
                    mounts_owned = json.loads(character.mounts_json)
                except Exception:
                    mounts_owned = []
            if character.minions_json:
                try:
                    minions_owned = json.loads(character.minions_json)
                except Exception:
                    minions_owned = []
            if character.achievements_json:
                try:
                    achievements_by_cat = json.loads(character.achievements_json)
                except Exception:
                    achievements_by_cat = {}
            if character.jobs_json:
                try:
                    raw_jobs = json.loads(character.jobs_json)
                    # Group by role in canonical order
                    role_map = {}
                    for job in raw_jobs:
                        r = job.get('role', 'Other')
                        role_map.setdefault(r, []).append(job)
                    for role in _ROLE_ORDER:
                        if role in role_map:
                            jobs_by_role.append((role, role_map[role]))
                    if 'Other' in role_map:
                        jobs_by_role.append(('Other', role_map['Other']))
                except Exception:
                    jobs_by_role = []
            rewards_earned = db.query(WebFfxivAchievementReward).filter_by(
                user_id=web_user_id
            ).order_by(desc(WebFfxivAchievementReward.awarded_at)).all()
            rewards_earned = [
                {
                    'name': r.achievement_name,
                    'xp': r.xp_awarded,
                    'legacy': r.legacy_awarded,
                    'awarded_at': r.awarded_at,
                }
                for r in rewards_earned
            ]

    # Fetch all FFXIV Collect catalogs (cached 6h each)
    catalog_error = False
    catalogs = {}
    _catalog_defs = [
        ('mounts',      'mounts'),
        ('minions',     'minions'),
        ('hairstyles',  'hairstyles'),
        ('emotes',      'emotes'),
        ('orchestrions','orchestrions'),
        ('spells',      'spells'),
        ('bardings',    'bardings'),
        ('fashions',    'fashions'),
        ('records',     'records'),
        ('achievements','achievements'),
        ('relics',      'relics'),
    ]
    def _cache_data_is_stale(data):
        """Return True if cached catalog has un-flattened dict fields (pre-_name() fix)."""
        if not data:
            return False
        sample = data[0]
        return isinstance(sample.get('category'), dict) or isinstance(sample.get('type'), dict)

    try:
        from app.discord_cache import get_cache
        cache = get_cache()
        for key, endpoint in _catalog_defs:
            cached = cache.get(f'ffxiv_collect_{key}')
            if cached and not _cache_data_is_stale(cached):
                catalogs[key] = cached
            else:
                if cached:
                    logger.info(f'FFXIV Collect cache for {key} has stale dict fields - re-fetching')
                data = _ffxiv_collect_catalog(endpoint, endpoint)
                catalogs[key] = data
                if data:
                    cache.set(f'ffxiv_collect_{key}', data, 21600)
    except Exception as e:
        logger.warning(f'FFXIV Collect catalog fetch failed: {e}')
        catalog_error = True
        for key, _ in _catalog_defs:
            catalogs.setdefault(key, [])

    # Fetch FFXIV Collect character profile for extra collection counts
    collect_char = None
    if character:
        collect_char = _ffxiv_collect_character(character.lodestone_id)

    def _enrich_owned(names, catalog):
        name_map = {m['name'].lower(): m for m in catalog}
        return [name_map.get(n.lower(), {'name': n, 'icon': '', 'url': '', 'owned_pct': ''}) | {'name': n} for n in names]

    def _missing(owned_names, catalog):
        owned_set = {n.lower() for n in owned_names}
        return [m for m in catalog if m['name'].lower() not in owned_set]

    mount_catalog = catalogs.get('mounts', [])
    minion_catalog = catalogs.get('minions', [])

    char_dict = None
    if character:
        cc = collect_char or {}

        def _cc_count(key):
            """Return count from FFXIV Collect character data, or None if 0/missing (private/unsynced)."""
            v = cc.get(key, {})
            if isinstance(v, dict):
                c = v.get('count')
                return c if c else None
            return None

        def _cc_total(key, catalog_key=None):
            """Return total from FFXIV Collect character data, falling back to catalog length."""
            v = cc.get(key, {})
            if isinstance(v, dict):
                t = v.get('total')
                if t:
                    return t
            return len(catalogs.get(catalog_key or key, []))

        # Relics: sum owned counts across sub-types (weapons/ultimate/armor/tools)
        relic_cc = cc.get('relics', {})
        relic_owned_count = sum(
            sub.get('count', 0) for sub in relic_cc.values() if isinstance(sub, dict)
        ) or None
        relic_total_count = sum(
            sub.get('total', 0) for sub in relic_cc.values() if isinstance(sub, dict)
        ) or len(catalogs.get('relics', []))

        char_dict = {
            'lodestone_id': character.lodestone_id,
            'character_name': character.character_name,
            'world': character.world,
            'datacenter': character.datacenter,
            'avatar_url': character.avatar_url,
            'portrait_url': character.portrait_url,
            'title': character.title,
            'free_company': character.free_company,
            'fc_tag': character.fc_tag,
            'active_job': character.active_job,
            'mount_count': character.mount_count,
            'minion_count': character.minion_count,
            'sync_status': character.sync_status,
            'sync_error': character.sync_error,
            'last_synced_at': character.last_synced_at,
            # FFXIV Collect counts - use character profile totals where available (more accurate than catalog length)
            'hairstyle_total':    _cc_total('hairstyles'),
            'hairstyle_count':    _cc_count('hairstyles'),
            'emote_total':        _cc_total('emotes'),
            'emote_count':        _cc_count('emotes'),
            'orchestrion_total':  _cc_total('orchestrions'),
            'orchestrion_count':  _cc_count('orchestrions'),
            'spell_total':        _cc_total('spells'),
            'spell_count':        _cc_count('spells'),
            'barding_total':      _cc_total('bardings'),
            'barding_count':      _cc_count('bardings'),
            'fashion_total':      _cc_total('fashions'),
            'fashion_count':      _cc_count('fashions'),
            'record_total':       _cc_total('records'),
            'record_count':       _cc_count('records'),
            'achievement_total':  sum(len(v) for v in achievements_by_cat.values()) or _cc_total('achievements'),
            'achievement_count':  sum(sum(1 for a in v if a.get('completed')) for v in achievements_by_cat.values()) or _cc_count('achievements'),
            'relic_owned_count':  relic_owned_count,
            'relic_total_count':  relic_total_count,
            'card_total':         _cc_total('cards') or 473,
            'card_count':         _cc_count('cards'),
            'collect_url': f'https://ffxivcollect.com/characters/{character.lodestone_id}',
        }

    # Group relics by type for accordion display
    relics_by_type = {}
    for relic in catalogs.get('relics', []):
        t = relic.get('type') or 'Other'
        relics_by_type.setdefault(t, []).append(relic)
    relics_grouped = sorted(relics_by_type.items(), key=lambda x: x[0])

    def _group_by_field(items, field, sort_key=None):
        """Group catalog items by a named string field. Returns sorted list of (group_name, [items])."""
        groups = {}
        for item in items:
            g = item.get(field) or 'Other'
            groups.setdefault(g, []).append(item)
        if sort_key:
            return sorted(groups.items(), key=sort_key)
        return sorted(groups.items(), key=lambda x: x[0])

    def _group_by_patch(items):
        """Group catalog items by major version (e.g. 2.x, 3.x). Returns sorted list of (label, [items])."""
        groups = {}
        for item in items:
            patch = str(item.get('patch') or '?')
            try:
                major = str(int(float(patch)))
            except (ValueError, TypeError):
                major = '?'
            label = f'Patch {major}.x' if major != '?' else 'Unknown'
            groups.setdefault(label, []).append(item)
        return sorted(groups.items(), key=lambda x: (x[0] == 'Unknown', x[0]))

    emotes_grouped = _group_by_field(catalogs.get('emotes', []), 'category')
    orchestrions_grouped = _group_by_field(catalogs.get('orchestrions', []), 'category')
    spells_grouped = _group_by_field(catalogs.get('spells', []), 'type')
    hairstyles_grouped = _group_by_patch(catalogs.get('hairstyles', []))
    bardings_grouped = _group_by_patch(catalogs.get('bardings', []))
    fashions_grouped = _group_by_patch(catalogs.get('fashions', []))
    records_grouped = _group_by_patch(catalogs.get('records', []))

    return render(request, 'questlog_web/ffxiv_collection.html', {
        'web_user': web_user,
        'active_page': 'ffxiv_collection',
        'character': char_dict,
        'character_json': json.dumps(char_dict) if char_dict else 'null',
        # Mounts/minions - fully owned via Lodestone scrape
        'mounts_owned': _enrich_owned(mounts_owned, mount_catalog) if character else [],
        'mounts_missing': _missing(mounts_owned, mount_catalog),
        'minions_owned': _enrich_owned(minions_owned, minion_catalog) if character else [],
        'minions_missing': _missing(minions_owned, minion_catalog),
        # Class/job levels grouped by role
        'jobs_by_role': jobs_by_role,
        # Catalogs grouped for accordion display
        'emotes_grouped':       emotes_grouped,
        'orchestrions_grouped': orchestrions_grouped,
        'spells_grouped':       spells_grouped,
        'hairstyles_grouped':   hairstyles_grouped,
        'bardings_grouped':     bardings_grouped,
        'fashions_grouped':     fashions_grouped,
        'records_grouped':      records_grouped,
        # Flat catalogs kept for backward compat / fallback
        'catalog_hairstyles':   catalogs.get('hairstyles', []),
        'catalog_emotes':       catalogs.get('emotes', []),
        'catalog_orchestrions': catalogs.get('orchestrions', []),
        'catalog_spells':       catalogs.get('spells', []),
        'catalog_bardings':     catalogs.get('bardings', []),
        'catalog_fashions':     catalogs.get('fashions', []),
        'catalog_records':      catalogs.get('records', []),
        'catalog_achievements': catalogs.get('achievements', []),
        'achievements_by_cat': achievements_by_cat,
        'relics_grouped':       relics_grouped,
        'relic_total':          len(catalogs.get('relics', [])),
        'mount_total': len(mount_catalog),
        'minion_total': len(minion_catalog),
        'rewards_earned': rewards_earned,
        'catalog_error': catalog_error,
    })
