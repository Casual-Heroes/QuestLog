# fluxer_webhooks.py - Queue embeds for the Fluxer bot to post to configured channels
#
# Called from Django views (synchronous) when events occur:
#   - lfg_announce: user posts an LFG group on QuestLog
#   - new_post: user creates a QuestLog social post
#   - new_member: new user registers
#   - giveaway_start: admin launches a giveaway
#   - giveaway_winner: admin picks a winner
#
# Inserts into fluxer_pending_broadcasts. The bot polls this table every 5s
# and sends the embed to the configured channel directly.

import json
import logging
import os
import time
from datetime import datetime, timezone
from sqlalchemy import text
from app.db import get_db_session
from app.questlog_web.models import WebFluxerWebhookConfig

logger = logging.getLogger(__name__)

# Default embed colors
BRAND_COLOR  = 0x5865F2   # QuestLog blue
GREEN_COLOR  = 0x57F287   # New member green
GOLD_COLOR   = 0xFEE75C   # LFG/giveaway gold
PINK_COLOR   = 0xEB459E   # Giveaway pink
ORANGE_COLOR = 0xFF7043   # LFG orange
LIVE_COLOR   = 0xF43F5E   # rose-500 - live stream


_SPEC_TO_ROLE = {
    'tank':    {'blood', 'vengeance', 'guardian', 'brewmaster', 'protection'},
    'healer':  {'restoration', 'preservation', 'mistweaver', 'holy', 'discipline',
                'white mage', 'whm', 'scholar', 'sch', 'astrologian', 'ast', 'sage', 'sge'},
    'dps':     {'frost', 'unholy', 'havoc', 'balance', 'feral', 'devastation',
                'beast mastery', 'marksmanship', 'survival', 'arcane', 'fire',
                'windwalker', 'retribution', 'shadow', 'assassination', 'outlaw', 'subtlety',
                'elemental', 'enhancement', 'affliction', 'demonology', 'destruction', 'arms', 'fury',
                'monk', 'mnk', 'dragoon', 'drg', 'ninja', 'nin', 'samurai', 'sam',
                'reaper', 'rpr', 'viper', 'vpr', 'bard', 'brd', 'machinist', 'mch',
                'dancer', 'dnc', 'black mage', 'blm', 'summoner', 'smn', 'red mage', 'rdm',
                'pictomancer', 'pct'},
    'support': {'augmentation'},
}
_DIRECT_ROLE_VALUES = {'tank', 'healer', 'dps', 'support', 'flex'}


def _infer_role_from_selections(sel: dict) -> str | None:
    """Infer tank/healer/dps/support from member selections (spec, class, or Role key)."""
    # Direct Role key (GW2, ESO, Palworld, custom)
    rv = sel.get('Role') or sel.get('role')
    if rv:
        rl = (rv[0] if isinstance(rv, list) else rv).lower().strip()
        if rl in _DIRECT_ROLE_VALUES:
            return rl
        # Survival/custom labels that map to slots
        for slot, names in _SPEC_TO_ROLE.items():
            if any(rl == n or n in rl for n in names):
                return slot

    # Specialization first (more specific), then Class
    for key in ('Specialization', 'Spec', 'specialization', 'spec', 'Job', 'job'):
        val = sel.get(key)
        if val:
            v = (val[0] if isinstance(val, list) else val).lower().strip()
            for slot, specs in _SPEC_TO_ROLE.items():
                if any(v == s or s in v for s in specs):
                    return slot

    return None


def _hex_to_int(hex_color: str | None, fallback: int) -> int:
    """Convert #RRGGBB hex string to int, falling back to provided default."""
    if hex_color:
        try:
            return int(hex_color.lstrip('#'), 16)
        except (ValueError, AttributeError):
            pass
    return fallback


def _format_template(template: str, **kwargs) -> str:
    """Replace {variable} placeholders in a message template."""
    for key, value in kwargs.items():
        template = template.replace('{' + key + '}', str(value))
    return template


def _queue_notification(event_type: str, embed_data: dict, default_color: int):
    """
    Look up the webhook config for this event type and insert into
    fluxer_pending_broadcasts so the bot can send it.
    """
    try:
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type=event_type, is_enabled=True
            ).first()
            if not cfg or not cfg.channel_id:
                return

            embed_data['color'] = _hex_to_int(cfg.embed_color, default_color)

            # Apply custom title/footer overrides if set
            if cfg.embed_title:
                embed_data['title'] = cfg.embed_title
            if cfg.embed_footer:
                embed_data['footer'] = cfg.embed_footer

            db.execute(text("""
                INSERT INTO fluxer_pending_broadcasts
                    (guild_id, channel_id, payload, created_at)
                VALUES (:guild_id, :channel_id, :payload, :now)
            """), {
                'guild_id': int(cfg.guild_id) if cfg.guild_id else 0,
                'channel_id': int(cfg.channel_id),
                'payload': json.dumps(embed_data),
                'now': int(time.time()),
            })
            db.commit()
    except Exception as e:
        logger.error(f"Failed to queue Fluxer notification for {event_type}: {e}")


def queue_lfg_embed_edit(group_id: int, group_platform: str, embed_data: dict,
                         pin_state: str | None = None):
    """
    Queue an in-place embed edit for every channel/thread that has a stored
    message for this LFG group (both Fluxer and Discord).

    pin_state: None = no change, "pin" = re-pin, "unpin" = unpin
    """
    try:
        with get_db_session() as db:
            rows = db.execute(text(
                "SELECT platform, guild_id, channel_id, message_id, thread_id "
                "FROM web_lfg_channel_messages "
                "WHERE group_id=:gid AND group_platform=:gp"
            ), {"gid": group_id, "gp": group_platform}).fetchall()

            if not rows:
                return

            now_ts = int(time.time())
            payload = dict(embed_data)
            payload['action'] = 'edit'
            payload['track_group_id'] = group_id
            payload['track_group_platform'] = group_platform
            if pin_state:
                payload['pin_state'] = pin_state

            for platform, guild_id, channel_id, message_id, thread_id in rows:
                payload_json = json.dumps(payload)
                if platform == 'discord':
                    db.execute(text(
                        "INSERT INTO discord_pending_broadcasts "
                        "(guild_id, channel_id, payload, created_at) "
                        "VALUES (:g, :c, :p, :t)"
                    ), {"g": int(guild_id), "c": int(thread_id or channel_id), "p": payload_json, "t": now_ts})
                else:
                    db.execute(text(
                        "INSERT INTO fluxer_pending_broadcasts "
                        "(guild_id, channel_id, payload, created_at) "
                        "VALUES (:g, :c, :p, :t)"
                    ), {"g": guild_id, "c": channel_id, "p": payload_json, "t": now_ts})
            db.commit()
    except Exception as e:
        logger.error(f"Failed to queue LFG embed edit for group {group_id}: {e}")


# ---------------------------------------------------------------------------
# Public API - call these from views
# ---------------------------------------------------------------------------

def build_lfg_embed_data(creator: str, game_name: str, title: str, description: str,
                         group_size: int, current_size: int, scheduled_time,
                         lfg_url: str, game_image_url: str | None = None,
                         tanks_needed: int = 0, healers_needed: int = 0,
                         dps_needed: int = 0, support_needed: int = 0,
                         use_roles: bool = False, role_schema: list | None = None,
                         duration_hours=None, creator_selections: dict | None = None,
                         group_id: int | None = None, voice_link: str | None = None,
                         group_platform: str = 'web', is_full: bool = False,
                         server_invite_link: str | None = None) -> dict:
    """Build and return the LFG embed data dict (does not queue anything)."""
    import json as _json
    from app.questlog_web.models import WebLFGMember, WebUser as _WebUser
    from app.questlog_web.views_discovery import (
        _SURVIVAL_SUB_CHOICES, _detect_survival_game_type,
    )

    desc_preview = description[:300] + '...' if description and len(description) > 300 else (description or '')

    size_label = f"{current_size}/{group_size}"
    if is_full:
        size_label += " - FULL"

    _is_survival_game = bool(_detect_survival_game_type(game_name))
    _size_field_name = "Server Size" if _is_survival_game else "Group Size"

    fields = [
        {"name": "Game",            "value": game_name,    "inline": True},
        {"name": _size_field_name,  "value": size_label,   "inline": True},
        {"name": "Posted by",       "value": creator,      "inline": True},
    ]

    # Fetch current members from DB if group_id provided
    member_roster = []  # list of (WebLFGMember, WebUser, selections_dict)
    creator_sel = creator_selections or {}
    if group_id:
        try:
            with get_db_session() as db:
                rows = db.query(WebLFGMember, _WebUser).join(
                    _WebUser, WebLFGMember.user_id == _WebUser.id
                ).filter(
                    WebLFGMember.group_id == group_id,
                    WebLFGMember.status == 'joined',
                ).all()
                for m, u in rows:
                    try:
                        sel = _json.loads(m.selections) if m.selections else {}
                    except Exception:
                        sel = {}
                    if m.is_creator:
                        creator_sel = sel
                    member_roster.append((m, u, sel))
        except Exception as e:
            logger.warning(f"build_lfg_embed_data: could not fetch members for group {group_id}: {e}")

    # Activity (from creator's selections)
    activity_val = creator_sel.get("Activity", "")
    if isinstance(activity_val, list):
        activity_val = ", ".join(str(a) for a in activity_val if a)
    elif isinstance(activity_val, str) and activity_val.startswith('['):
        try:
            activity_val = ", ".join(str(a) for a in _json.loads(activity_val) if a)
        except Exception:
            pass
    elif not isinstance(activity_val, str):
        activity_val = str(activity_val) if activity_val else ""
    if activity_val:
        fields.append({"name": "🎮 Activity", "value": activity_val, "inline": True})

    # Survival / generic template fields - show any selections not already shown above
    _already_shown = {"Activity"}
    _field_icons = {"Platform": "🖥️", "Experience": "⭐", "Server Type": "🌐", "Server Info": "📋"}
    for _sel_key, _sel_val in creator_sel.items():
        if _sel_key in _already_shown:
            continue
        if isinstance(_sel_val, list):
            _sel_str = ", ".join(str(v) for v in _sel_val if v)
        elif isinstance(_sel_val, str) and _sel_val.startswith('['):
            try:
                _parsed = _json.loads(_sel_val)
                _sel_str = ", ".join(str(v) for v in _parsed if v)
            except Exception:
                _sel_str = _sel_val.strip()
        else:
            _sel_str = str(_sel_val).strip() if _sel_val else ""
        if not _sel_str:
            continue
        _icon = _field_icons.get(_sel_key, "")
        _label = f"{_icon} {_sel_key}" if _icon else _sel_key
        fields.append({"name": _label, "value": _sel_str, "inline": True})

    # When and Duration - skip for survival games (servers are always-on, no session concept)
    if not _is_survival_game:
        if scheduled_time:
            try:
                dt = datetime.fromtimestamp(int(scheduled_time), tz=timezone.utc)
                fields.append({"name": "📅 When", "value": dt.strftime("%a, %b %-d at %-I:%M %p UTC"), "inline": True})
            except (ValueError, TypeError, OSError):
                pass
        else:
            fields.append({"name": "📅 When", "value": "Now / Flexible", "inline": True})

        if duration_hours:
            dur = duration_hours
            dur_text = f"{int(dur)}h" if dur == int(dur) else f"{dur}h"
        else:
            dur_text = "-"
        fields.append({"name": "⏱️ Duration", "value": dur_text, "inline": True})

    # Role slots with member roster
    if use_roles:
        schema = role_schema or []
        is_survival = bool(_detect_survival_game_type(game_name)) and any(
            r.get('slot') == 'tank' and (r.get('label') == 'Combat' or r.get('color') == 'orange')
            for r in schema
        )
        slot_icons = {'tank': '🛡', 'healer': '💚', 'dps': '⚔', 'support': '🔧'}
        slot_names = {'tank': 'Tank', 'healer': 'Healer', 'dps': 'DPS', 'support': 'Support'}

        if is_survival:
            surv_key = _detect_survival_game_type(game_name)
            sub_choices = _SURVIVAL_SUB_CHOICES.get(surv_key, [])
            sub_to_slot = {label: slot for label, slot in sub_choices}
            slot_members = {'tank': [], 'healer': [], 'dps': [], 'support': []}
            for m, u, sel in member_roster:
                role_sel = sel.get("Role", "")
                if isinstance(role_sel, list):
                    role_sel = role_sel[0] if role_sel else ""
                mapped_slot = sub_to_slot.get(role_sel)
                uname = u.display_name or u.username
                platform_val = sel.get("Platform", "")
                if isinstance(platform_val, list):
                    platform_val = platform_val[0] if platform_val else ""
                if role_sel and platform_val:
                    line = f"@{uname} - {role_sel}, {platform_val}"
                elif role_sel:
                    line = f"@{uname} - {role_sel}"
                elif platform_val:
                    line = f"@{uname} - {platform_val}"
                else:
                    line = f"@{uname}"
                slot_members[mapped_slot if mapped_slot else 'dps'].append(line)
            for slot in ('tank', 'healer', 'dps', 'support'):
                members_in = slot_members[slot]
                if members_in:
                    fields.append({
                        "name": f"{slot_icons[slot]} {slot_names[slot]} ({len(members_in)})",
                        "value": "\n".join(members_in[:8]),
                        "inline": True,
                    })
        else:
            slot_labels = {r['slot']: r['label'] for r in schema} if schema else {}
            slot_needed = {'tank': tanks_needed, 'healer': healers_needed, 'dps': dps_needed, 'support': support_needed}
            slot_members = {'tank': [], 'healer': [], 'dps': [], 'support': [], 'unassigned': []}
            for m, u, sel in member_roster:
                uname = u.display_name or u.username
                cls_val = sel.get("Class") or sel.get("Job") or ""
                if isinstance(cls_val, list):
                    cls_val = cls_val[0] if cls_val else ""
                spec_val = sel.get("Specialization") or sel.get("Spec") or sel.get("Subclass") or ""
                if isinstance(spec_val, list):
                    spec_val = spec_val[0] if spec_val else ""
                # Unified format: "Class - Spec" matching the web portal display
                if cls_val and spec_val and spec_val != cls_val:
                    display_cls = f"{cls_val} - {spec_val}"
                else:
                    display_cls = cls_val or spec_val
                platform_val = sel.get("Platform", "")
                if isinstance(platform_val, list):
                    platform_val = platform_val[0] if platform_val else ""
                if display_cls and platform_val:
                    line = f"@{uname} - {display_cls}, {platform_val}"
                elif display_cls:
                    line = f"@{uname} - {display_cls}"
                elif platform_val:
                    line = f"@{uname} - {platform_val}"
                else:
                    line = f"@{uname}"
                # Bucket by stored role (normalize to lowercase), fall back to inferring from selections
                _stored_role = (m.role or '').lower() or None
                bucket = _stored_role if _stored_role in slot_members else _infer_role_from_selections(sel)
                if bucket not in slot_members:
                    bucket = 'unassigned'
                slot_members[bucket].append(line)
            any_bucketed = any(slot_members[s] for s in ('tank', 'healer', 'dps', 'support'))
            if any_bucketed:
                for slot in ('tank', 'healer', 'dps', 'support'):
                    needed = slot_needed[slot]
                    members_in = slot_members[slot]
                    if needed or members_in:
                        label = slot_labels.get(slot, slot_names[slot])
                        val = "\n".join(members_in[:8]) if members_in else "-"
                        fields.append({
                            "name": f"{slot_icons[slot]} {label} ({len(members_in)}/{needed})",
                            "value": val,
                            "inline": True,
                        })
                if slot_members['unassigned']:
                    fields.append({
                        "name": f"❓ Unassigned ({len(slot_members['unassigned'])})",
                        "value": "\n".join(slot_members['unassigned'][:8]),
                        "inline": True,
                    })
            elif slot_members['unassigned']:
                # All members unassigned (role not stored) - show flat member list
                fields.append({
                    "name": f"👥 Members ({len(slot_members['unassigned'])})",
                    "value": "\n".join(slot_members['unassigned'][:8]),
                    "inline": True,
                })

    if server_invite_link:
        _sil = server_invite_link.lower()
        if 'discord.gg' in _sil or 'discord.com/invite' in _sil:
            _join_label = 'Join on Discord'
        elif 'fluxer' in _sil:
            _join_label = 'Join on Fluxer'
        elif 'stoat' in _sil:
            _join_label = 'Join on Stoat'
        elif 'teamspeak' in _sil or 'ts3' in _sil:
            _join_label = 'Join TeamSpeak'
        elif 'mumble' in _sil:
            _join_label = 'Join Mumble'
        else:
            _join_label = 'Join our Server'
        fields.append({"name": "Join Server", "value": f"[{_join_label}]({server_invite_link})", "inline": True})

    footer = "QuestLog LFG - questlog.casual-heroes.com/"
    if voice_link:
        footer += f" | {voice_link}"

    title_prefix = "FULL - " if is_full else "LFG: "
    embed_data = {
        "title": f"{title_prefix}{title}",
        "description": desc_preview or "",
        "url": lfg_url,
        "fields": fields,
        "footer": footer,
    }
    if game_image_url:
        embed_data["thumbnail"] = game_image_url
    if group_id:
        embed_data["track_group_id"] = group_id
        embed_data["track_group_platform"] = group_platform

    return embed_data


def notify_lfg_post(creator: str, game_name: str, title: str, description: str,
                    group_size: int, current_size: int, scheduled_time,
                    lfg_url: str, game_image_url: str | None = None,
                    tanks_needed: int = 0, healers_needed: int = 0,
                    dps_needed: int = 0, support_needed: int = 0,
                    use_roles: bool = False, role_schema: list | None = None,
                    duration_hours=None, creator_selections: dict | None = None,
                    group_id: int | None = None, voice_link: str | None = None,
                    group_platform: str = 'web', server_invite_link: str | None = None):
    """Queue a rich embed when a new LFG group is posted on QuestLog.
    Sends to all guilds subscribed via web_community_bot_configs (both Fluxer and Discord).
    """
    embed_data = build_lfg_embed_data(
        creator=creator, game_name=game_name, title=title, description=description,
        group_size=group_size, current_size=current_size, scheduled_time=scheduled_time,
        lfg_url=lfg_url, game_image_url=game_image_url,
        tanks_needed=tanks_needed, healers_needed=healers_needed,
        dps_needed=dps_needed, support_needed=support_needed,
        use_roles=use_roles, role_schema=role_schema, duration_hours=duration_hours,
        creator_selections=creator_selections, group_id=group_id, voice_link=voice_link,
        group_platform=group_platform, server_invite_link=server_invite_link,
    )
    embed_data['color'] = ORANGE_COLOR

    try:
        with get_db_session() as db:
            subscribers = db.execute(text(
                "SELECT platform, guild_id, channel_id FROM web_community_bot_configs "
                "WHERE event_type='lfg_announce' AND is_enabled=1 AND channel_id IS NOT NULL"
            )).fetchall()

            now_ts = int(time.time())
            for platform, guild_id, channel_id in subscribers:
                try:
                    payload = json.dumps(embed_data)
                    if platform == 'discord':
                        db.execute(text(
                            "INSERT INTO discord_pending_broadcasts "
                            "(guild_id, channel_id, payload, created_at) "
                            "VALUES (:g, :c, :p, :t)"
                        ), {'g': int(guild_id), 'c': int(channel_id), 'p': payload, 't': now_ts})
                    else:
                        db.execute(text(
                            "INSERT INTO fluxer_pending_broadcasts "
                            "(guild_id, channel_id, payload, created_at) "
                            "VALUES (:g, :c, :p, :t)"
                        ), {'g': guild_id, 'c': channel_id, 'p': payload, 't': now_ts})
                except Exception as e:
                    logger.error(f"Failed to queue LFG announce for {platform} guild {guild_id}: {e}")
            db.commit()
    except Exception as e:
        logger.error(f"notify_lfg_post fan-out failed: {e}")


def queue_lfg_embed_edit_for_group(group_id: int, group_platform: str = 'web',
                                   pin_state: str | None = None):
    """
    Rebuild the full LFG embed from DB and queue an in-place edit to every
    channel/thread that has a stored message for this group.
    Call this after any join, leave, or status change.
    """
    try:
        from app.questlog_web.models import WebLFGGroup, WebUser as _WU
        with get_db_session() as db:
            if group_platform == 'web':
                group = db.query(WebLFGGroup).filter_by(id=group_id).first()
                if not group:
                    return
                creator_row = db.query(_WU).filter_by(id=group.creator_id).first()
                creator_name = (creator_row.display_name or creator_row.username) if creator_row else 'Unknown'
                lfg_url = f"https://questlog.casual-heroes.com/lfg/{group.share_token or group.id}/"
                is_full = group.status == 'full'

                from app.questlog_web.views_discovery import _parse_role_schema
                embed_data = build_lfg_embed_data(
                    creator=creator_name,
                    game_name=group.game_name,
                    title=group.title,
                    description=group.description or '',
                    group_size=group.group_size,
                    current_size=group.current_size,
                    scheduled_time=group.scheduled_time,
                    lfg_url=lfg_url,
                    game_image_url=group.game_image_url,
                    use_roles=group.use_roles or False,
                    tanks_needed=group.tanks_needed or 0,
                    healers_needed=group.healers_needed or 0,
                    dps_needed=group.dps_needed or 0,
                    support_needed=group.support_needed or 0,
                    role_schema=_parse_role_schema(group.role_schema),
                    duration_hours=group.duration_hours,
                    voice_link=group.voice_link,
                    group_id=group_id,
                    group_platform=group_platform,
                    is_full=is_full,
                )
        queue_lfg_embed_edit(group_id, group_platform, embed_data, pin_state=pin_state)
    except Exception as e:
        logger.error(f"queue_lfg_embed_edit_for_group failed for group {group_id}: {e}")


def notify_member_signup_log(username: str, profile_url: str):
    """Post a staff-only audit log entry when a new QuestLog account is verified.
    Queues to the private Fluxer and Discord staff log channels defined in warden.env.
    """
    _fluxer_ch = os.environ.get('FLUXER_LOG_CHANNEL', '').strip()
    _discord_ch = os.environ.get('DISCORD_LOG_CHANNEL', '').strip()
    if not _fluxer_ch and not _discord_ch:
        return
    try:
        FLUXER_LOG_CHANNEL = int(_fluxer_ch) if _fluxer_ch else None
        DISCORD_LOG_CHANNEL = int(_discord_ch) if _discord_ch else None
    except ValueError:
        logger.error("FLUXER_LOG_CHANNEL or DISCORD_LOG_CHANNEL in env is not a valid integer")
        return

    embed_data = {
        "title": "New QuestLog Member",
        "description": f"**{username}** just verified their account.\n[View Profile]({profile_url})",
        "footer": "QuestLog signup log",
        "color": BRAND_COLOR,
    }
    payload_json = json.dumps(embed_data)
    now_ts = int(time.time())

    try:
        with get_db_session() as db:
            if FLUXER_LOG_CHANNEL:
                db.execute(text(
                    "INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                    "VALUES (:g, :c, :p, :t)"
                ), {"g": 0, "c": FLUXER_LOG_CHANNEL, "p": payload_json, "t": now_ts})
            if DISCORD_LOG_CHANNEL:
                db.execute(text(
                    "INSERT INTO discord_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                    "VALUES (:g, :c, :p, :t)"
                ), {"g": 0, "c": DISCORD_LOG_CHANNEL, "p": payload_json, "t": now_ts})
            db.commit()
    except Exception as e:
        logger.error(f"Failed to queue member signup log: {e}")


def queue_lfg_embed_edit_for_group(group_id: int, group_platform: str = 'web',
                                   pin_state: str | None = None):
    """
    Rebuild the full LFG embed from DB and queue an in-place edit to every
    channel/thread that has a stored message for this group.
    Call this after any join, leave, or status change.
    """
    try:
        from app.questlog_web.models import WebLFGGroup, WebUser as _WU
        with get_db_session() as db:
            if group_platform == 'web':
                group = db.query(WebLFGGroup).filter_by(id=group_id).first()
                if not group:
                    return
                creator_row = db.query(_WU).filter_by(id=group.creator_id).first()
                creator_name = (creator_row.display_name or creator_row.username) if creator_row else 'Unknown'
                lfg_url = f"https://questlog.casual-heroes.com/lfg/{group.share_token or group.id}/"
                is_full = group.status == 'full'

                from app.questlog_web.views_discovery import _parse_role_schema
                embed_data = build_lfg_embed_data(
                    creator=creator_name,
                    game_name=group.game_name,
                    title=group.title,
                    description=group.description or '',
                    group_size=group.group_size,
                    current_size=group.current_size,
                    scheduled_time=group.scheduled_time,
                    lfg_url=lfg_url,
                    game_image_url=group.game_image_url,
                    use_roles=group.use_roles or False,
                    tanks_needed=group.tanks_needed or 0,
                    healers_needed=group.healers_needed or 0,
                    dps_needed=group.dps_needed or 0,
                    support_needed=group.support_needed or 0,
                    role_schema=_parse_role_schema(group.role_schema),
                    duration_hours=group.duration_hours,
                    voice_link=group.voice_link,
                    group_id=group_id,
                    group_platform=group_platform,
                    is_full=is_full,
                )
        queue_lfg_embed_edit(group_id, group_platform, embed_data, pin_state=pin_state)
    except Exception as e:
        logger.error(f"queue_lfg_embed_edit_for_group failed for group {group_id}: {e}")


def notify_member_signup_log(username: str, profile_url: str):
    """Post a staff-only audit log entry when a new QuestLog account is verified.
    Queues to the private Fluxer and Discord staff log channels defined in warden.env.
    """
    _fluxer_ch = os.environ.get('FLUXER_LOG_CHANNEL', '').strip()
    _discord_ch = os.environ.get('DISCORD_LOG_CHANNEL', '').strip()
    if not _fluxer_ch and not _discord_ch:
        return
    try:
        FLUXER_LOG_CHANNEL = int(_fluxer_ch) if _fluxer_ch else None
        DISCORD_LOG_CHANNEL = int(_discord_ch) if _discord_ch else None
    except ValueError:
        logger.error("FLUXER_LOG_CHANNEL or DISCORD_LOG_CHANNEL in env is not a valid integer")
        return

    embed_data = {
        "title": "New QuestLog Member",
        "description": f"**{username}** just verified their account.\n[View Profile]({profile_url})",
        "footer": "QuestLog signup log",
        "color": BRAND_COLOR,
    }
    payload_json = json.dumps(embed_data)
    now_ts = int(time.time())

    try:
        with get_db_session() as db:
            if FLUXER_LOG_CHANNEL:
                db.execute(text(
                    "INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                    "VALUES (:g, :c, :p, :t)"
                ), {"g": 0, "c": FLUXER_LOG_CHANNEL, "p": payload_json, "t": now_ts})
            if DISCORD_LOG_CHANNEL:
                db.execute(text(
                    "INSERT INTO discord_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                    "VALUES (:g, :c, :p, :t)"
                ), {"g": 0, "c": DISCORD_LOG_CHANNEL, "p": payload_json, "t": now_ts})
            db.commit()
    except Exception as e:
        logger.error(f"Failed to queue member signup log: {e}")


def notify_new_member(username: str, profile_url: str):
    """Queue an embed when a new user registers on QuestLog."""
    try:
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='new_member', is_enabled=True
            ).first()
            if not cfg or not cfg.channel_id:
                return

            # Use custom message template if set, else default
            if cfg.message_template:
                body = _format_template(
                    cfg.message_template,
                    username=username,
                    profile=profile_url,
                )
            else:
                body = f"Welcome **{username}** to QuestLog!\n\n[View Profile]({profile_url})"

            embed_data = {
                "title": cfg.embed_title or "New Member Joined QuestLog!",
                "description": body,
                "footer": cfg.embed_footer or "QuestLog - questlog.casual-heroes.com/",
                "color": _hex_to_int(cfg.embed_color, GREEN_COLOR),
            }

            db.execute(text("""
                INSERT INTO fluxer_pending_broadcasts
                    (guild_id, channel_id, payload, created_at)
                VALUES (:guild_id, :channel_id, :payload, :now)
            """), {
                'guild_id': int(cfg.guild_id) if cfg.guild_id else 0,
                'channel_id': int(cfg.channel_id),
                'payload': json.dumps(embed_data),
                'now': int(time.time()),
            })
            db.commit()
    except Exception as e:
        logger.error(f"Failed to queue Fluxer new_member notification: {e}")


def _post_embed_data(username: str, game: str, content: str, post_url: str, image_url: str | None, prefix: str) -> dict:
    """Build shared embed dict for new/edited posts."""
    preview = content[:300] + "..." if len(content) > 300 else content
    title = f"{prefix} - {username} - Posted About {game}" if game else f"{prefix} - {username}"
    desc = preview
    embed = {
        "title": title,
        "description": desc,
        "url": post_url,
        "footer": "QuestLog - questlog.casual-heroes.com/",
    }
    if image_url:
        embed["image"] = image_url
    return embed


def notify_new_post(username: str, game: str, content: str, post_url: str,
                    image_url: str | None = None, post_id: int | None = None):
    """Queue a Fluxer embed when any user creates a QuestLog post."""
    embed_data = _post_embed_data(username, game, content, post_url, image_url, "\U0001f4dd New Post")
    if post_id:
        embed_data['track_post_id'] = post_id
    _queue_notification("new_post", embed_data, BRAND_COLOR)


def notify_post_edit(username: str, game: str, content: str, post_url: str,
                     image_url: str | None = None, post_id: int | None = None):
    """Edit the existing Fluxer broadcast message in-place, or post new if none tracked."""
    embed_data = _post_embed_data(username, game, content, post_url, image_url, "\U0001f4dd New Post")
    if not post_id:
        _queue_notification("new_post", embed_data, BRAND_COLOR)
        return
    try:
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='new_post', is_enabled=True
            ).first()
            if not cfg or not cfg.channel_id:
                return
            embed_data['color'] = _hex_to_int(cfg.embed_color, BRAND_COLOR)
            tracked = db.execute(text(
                "SELECT message_id FROM web_post_broadcast_messages "
                "WHERE post_id=:pid AND platform='fluxer' LIMIT 1"
            ), {'pid': post_id}).fetchone()
            if tracked:
                embed_data['action'] = 'edit'
                embed_data['track_post_id'] = post_id
            else:
                embed_data['track_post_id'] = post_id
            db.execute(text("""
                INSERT INTO fluxer_pending_broadcasts
                    (guild_id, channel_id, payload, created_at)
                VALUES (:guild_id, :channel_id, :payload, :now)
            """), {
                'guild_id': int(cfg.guild_id) if cfg.guild_id else 0,
                'channel_id': int(cfg.channel_id),
                'payload': json.dumps(embed_data),
                'now': int(time.time()),
            })
            db.commit()
    except Exception as e:
        logger.error(f"notify_post_edit failed: {e}")


def notify_post_delete(post_id: int):
    """Queue deletion of the Fluxer broadcast message for a deleted post."""
    try:
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='new_post', is_enabled=True
            ).first()
            if not cfg or not cfg.channel_id:
                return
            tracked = db.execute(text(
                "SELECT message_id FROM web_post_broadcast_messages "
                "WHERE post_id=:pid AND platform='fluxer' LIMIT 1"
            ), {'pid': post_id}).fetchone()
            if not tracked:
                return
            payload = {'action': 'delete', 'track_post_id': post_id}
            db.execute(text("""
                INSERT INTO fluxer_pending_broadcasts
                    (guild_id, channel_id, payload, created_at)
                VALUES (:guild_id, :channel_id, :payload, :now)
            """), {
                'guild_id': int(cfg.guild_id) if cfg.guild_id else 0,
                'channel_id': int(cfg.channel_id),
                'payload': json.dumps(payload),
                'now': int(time.time()),
            })
            db.commit()
    except Exception as e:
        logger.error(f"notify_post_delete (fluxer) failed: {e}")


def notify_new_post_discord(username: str, game: str, content: str, post_url: str,
                            image_url: str | None = None, post_id: int | None = None):
    """POST a Discord embed via webhook and store the message ID for future edits/deletes."""
    _send_post_discord_webhook(username, game, content, post_url, image_url,
                               "\U0001f4dd New Post", post_id=post_id, action='new')


def notify_post_edit_discord(username: str, game: str, content: str, post_url: str,
                              image_url: str | None = None, post_id: int | None = None):
    """Edit the existing Discord webhook message in-place, or post new if none tracked."""
    _send_post_discord_webhook(username, game, content, post_url, image_url,
                               "\U0001f4dd New Post", post_id=post_id, action='edit')


def notify_post_delete_discord(post_id: int):
    """Delete the Discord webhook message for a deleted post."""
    if not post_id:
        return
    try:
        import requests as _req
        with get_db_session() as db:
            row = db.execute(text(
                "SELECT message_id, webhook_url FROM web_post_broadcast_messages "
                "WHERE post_id=:pid AND platform='discord' LIMIT 1"
            ), {'pid': post_id}).fetchone()
            if not row:
                return
            msg_id, webhook_url = row
        if webhook_url and msg_id:
            _req.delete(f"{webhook_url}/messages/{msg_id}", timeout=5)
        with get_db_session() as db:
            db.execute(text(
                "DELETE FROM web_post_broadcast_messages WHERE post_id=:pid AND platform='discord'"
            ), {'pid': post_id})
            db.commit()
    except Exception as e:
        logger.error(f"notify_post_delete_discord failed: {e}")


def _send_post_discord_webhook(username: str, game: str, content: str, post_url: str,
                               image_url: str | None, prefix: str,
                               post_id: int | None = None, action: str = 'new'):
    try:
        import requests as _req
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='new_post', is_enabled=True
            ).first()
            if not cfg or not cfg.discord_webhook_url:
                return
            webhook_url = cfg.discord_webhook_url
            existing_msg_id = None
            if post_id:
                row = db.execute(text(
                    "SELECT message_id FROM web_post_broadcast_messages "
                    "WHERE post_id=:pid AND platform='discord' LIMIT 1"
                ), {'pid': post_id}).fetchone()
                if row:
                    existing_msg_id = row[0]

        preview = content[:300] + "..." if len(content) > 300 else content
        title = f"{prefix} - {username} - Posted About {game}" if game else f"{prefix} - {username}"
        embed = {
            "title": title,
            "description": preview,
            "url": post_url,
            "color": BRAND_COLOR,
            "footer": {"text": "QuestLog - questlog.casual-heroes.com/"},
        }
        if image_url:
            embed["image"] = {"url": image_url}

        if action == 'edit' and existing_msg_id:
            # Edit the existing webhook message
            resp = _req.patch(
                f"{webhook_url}/messages/{existing_msg_id}",
                json={"embeds": [embed]},
                timeout=5,
            )
        else:
            # New post - use ?wait=true to get message ID back
            resp = _req.post(f"{webhook_url}?wait=true", json={"embeds": [embed]}, timeout=5)
            if post_id and resp.status_code == 200:
                msg_id = resp.json().get('id')
                if msg_id:
                    with get_db_session() as db:
                        db.execute(text("""
                            INSERT INTO web_post_broadcast_messages
                                (post_id, platform, channel_id, message_id, webhook_url, created_at)
                            VALUES (:pid, 'discord', :ch, :mid, :wurl, :now)
                            ON DUPLICATE KEY UPDATE message_id=:mid, webhook_url=:wurl
                        """), {
                            'pid': post_id, 'ch': '0', 'mid': str(msg_id),
                            'wurl': webhook_url, 'now': int(time.time()),
                        })
                        db.commit()
    except Exception as e:
        logger.error(f"Failed to send Discord post webhook: {e}")


def notify_new_comment(username: str, post_author: str, comment: str, post_url: str):
    """Queue a Fluxer embed when any user replies to a QuestLog post."""
    preview = comment[:200] + "..." if len(comment) > 200 else comment
    embed_data = {
        "title": f"\U0001f4ac {username} replied to {post_author}'s post",
        "description": preview,
        "url": post_url,
        "footer": "QuestLog - questlog.casual-heroes.com/",
    }
    _queue_notification("new_post", embed_data, BRAND_COLOR)


def notify_new_comment_discord(username: str, post_author: str, comment: str, post_url: str):
    """POST a Discord embed via webhook when any user replies to a QuestLog post."""
    try:
        import requests as _req
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='new_post', is_enabled=True
            ).first()
            if not cfg or not cfg.discord_webhook_url:
                return
            webhook_url = cfg.discord_webhook_url

        preview = comment[:200] + "..." if len(comment) > 200 else comment
        embed = {
            "title": f"\U0001f4ac {username} replied to {post_author}'s post",
            "description": preview,
            "url": post_url,
            "color": BRAND_COLOR,
            "footer": {"text": "QuestLog - questlog.casual-heroes.com/"},
        }
        _req.post(webhook_url, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        logger.error(f"Failed to send Discord new_comment webhook: {e}")


def notify_giveaway_start(title: str, prize: str, giveaway_url: str):
    """Queue an embed when a giveaway is launched."""
    embed_data = {
        "title": f"Giveaway Started: {title}",
        "description": (
            f"**Prize:** {prize}\n\n"
            f"[Enter the Giveaway]({giveaway_url})"
        ),
        "url": giveaway_url,
        "footer": "Good luck! | questlog.casual-heroes.com/giveaways/",
    }
    _queue_notification("giveaway_start", embed_data, PINK_COLOR)


def notify_go_live(username: str, platform: str, title: str, stream_url: str, profile_url: str):
    """Queue an embed when a QuestLog user goes live on Twitch or YouTube."""
    platform_label = 'Twitch' if platform == 'twitch' else 'YouTube'
    icon = '\U0001f534' if platform == 'twitch' else '\U0001f4fa'   # red circle / TV
    embed_data = {
        'title': f'{icon} {username} is live on {platform_label}!',
        'description': (
            f'**{title}**\n\n'
            f'[Watch Stream]({stream_url}) | [QuestLog Profile]({profile_url})'
        ),
        'url': stream_url,
        'footer': 'QuestLog Live - questlog.casual-heroes.com/',
    }
    _queue_notification('go_live', embed_data, LIVE_COLOR)


def notify_giveaway_winner(title: str, winner_names: list[str], giveaway_url: str):
    """Queue an embed when a giveaway winner is picked."""
    if len(winner_names) == 1:
        winner_text = f"Congratulations to **{winner_names[0]}**!"
    else:
        winners_str = ", ".join(f"**{w}**" for w in winner_names)
        winner_text = f"Winners: {winners_str}"

    embed_data = {
        "title": f"Giveaway Ended: {title}",
        "description": (
            f"{winner_text}\n\n"
            f"[View Giveaway]({giveaway_url})"
        ),
        "url": giveaway_url,
        "footer": "QuestLog Giveaways | questlog.casual-heroes.com/giveaways/",
    }
    _queue_notification("giveaway_winner", embed_data, GOLD_COLOR)


# ---------------------------------------------------------------------------
# Job Guide notifications - driven by web_fluxer_webhook_configs event_type='ffxiv_guide'
# ---------------------------------------------------------------------------

_GUIDE_COLOR = 0x7B68EE   # medium slate blue


def notify_new_job_guide(job_name: str, author: str, title: str, guide_url: str):
    """Queue Fluxer + Discord broadcasts when a new job guide is published.

    Reads channel/webhook config from web_fluxer_webhook_configs (event_type='ffxiv_guide')
    so admins can control destinations from the admin panel without code changes.
    """
    desc = (
        f"**{author}** just published a new **{job_name}** guide!\n\n"
        f"**{title}**\n\n"
        f"[Read the guide]({guide_url})"
    )
    embed_data = {
        "title": f"\U0001f4d6 New {job_name} Guide",
        "description": desc,
        "url": guide_url,
        "color": _GUIDE_COLOR,
        "footer": "QuestLog Job Guides | questlog.casual-heroes.com/ffxiv/tools/job-guides/",
    }

    try:
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='ffxiv_guide', is_enabled=True
            ).first()
            if not cfg:
                return

            embed_data['color'] = _hex_to_int(cfg.embed_color, _GUIDE_COLOR)

            now = int(time.time())

            # Fluxer channel
            if cfg.channel_id:
                payload = dict(embed_data)
                if cfg.mention_role_id:
                    payload['content'] = f'<@&{cfg.mention_role_id}>'
                db.execute(text(
                    "INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                    "VALUES (:g, :c, :p, :t)"
                ), {
                    'g': int(cfg.guild_id) if cfg.guild_id else 0,
                    'c': int(cfg.channel_id),
                    'p': json.dumps(payload),
                    't': now,
                })

            # Discord - WardenBot picks up discord_pending_broadcasts
            # action=direct posts straight to channel without creating a thread
            if cfg.discord_webhook_url:
                _fire_discord_guide_webhook(cfg.discord_webhook_url, embed_data)

            db.commit()
    except Exception as e:
        logger.error(f"notify_new_job_guide: failed to queue broadcasts: {e}")


def _fire_discord_guide_webhook(webhook_url: str, embed_data: dict):
    """POST a job guide embed to a Discord webhook URL."""
    try:
        import urllib.request as _req
        discord_embed = dict(embed_data)
        # Convert footer string to Discord object format
        if isinstance(discord_embed.get('footer'), str):
            discord_embed['footer'] = {'text': discord_embed['footer']}
        data = json.dumps({'embeds': [discord_embed]}).encode()
        req = _req.Request(
            webhook_url, data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'QuestLog/1.0'},
        )
        with _req.urlopen(req, timeout=10):
            pass
    except Exception as e:
        logger.warning(f"notify_new_job_guide: Discord webhook failed: {e}")
