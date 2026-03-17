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
                         group_platform: str = 'web', is_full: bool = False) -> dict:
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

    fields = [
        {"name": "Game",       "value": game_name,    "inline": True},
        {"name": "Group Size", "value": size_label,   "inline": True},
        {"name": "Posted by",  "value": creator,      "inline": True},
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
    elif not isinstance(activity_val, str):
        activity_val = str(activity_val) if activity_val else ""
    if activity_val:
        fields.append({"name": "🎮 Activity", "value": activity_val, "inline": True})

    # When
    if scheduled_time:
        try:
            dt = datetime.fromtimestamp(int(scheduled_time), tz=timezone.utc)
            fields.append({"name": "📅 When", "value": dt.strftime("%a, %b %-d at %-I:%M %p UTC"), "inline": True})
        except (ValueError, TypeError, OSError):
            pass
    else:
        fields.append({"name": "📅 When", "value": "Now / Flexible", "inline": True})

    # Duration
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

    footer = "QuestLog LFG - casual-heroes.com/ql/"
    if voice_link:
        footer += f" | {voice_link}"

    title_prefix = "FULL - " if is_full else "LFG: "
    embed_data = {
        "title": f"{title_prefix}{title}",
        "description": desc_preview if desc_preview else f"Posted by **{creator}**",
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
                    group_platform: str = 'web'):
    """Queue a rich embed when a new LFG group is posted on QuestLog."""
    embed_data = build_lfg_embed_data(
        creator=creator, game_name=game_name, title=title, description=description,
        group_size=group_size, current_size=current_size, scheduled_time=scheduled_time,
        lfg_url=lfg_url, game_image_url=game_image_url,
        tanks_needed=tanks_needed, healers_needed=healers_needed,
        dps_needed=dps_needed, support_needed=support_needed,
        use_roles=use_roles, role_schema=role_schema, duration_hours=duration_hours,
        creator_selections=creator_selections, group_id=group_id, voice_link=voice_link,
        group_platform=group_platform,
    )
    _queue_notification("lfg_announce", embed_data, ORANGE_COLOR)


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
                lfg_url = f"https://casual-heroes.com/ql/lfg/{group.share_token or group.id}/"
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
                "footer": cfg.embed_footer or "QuestLog - casual-heroes.com/ql/",
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


def notify_new_post(username: str, game: str, content: str, post_url: str):
    """Queue an embed when a new QuestLog post is created."""
    preview = content[:300] + "..." if len(content) > 300 else content
    embed_data = {
        "title": f"{username} posted about {game}" if game else f"{username} posted on QuestLog",
        "description": preview,
        "url": post_url,
        "footer": "QuestLog - casual-heroes.com/ql/",
    }
    _queue_notification("new_post", embed_data, BRAND_COLOR)


def notify_giveaway_start(title: str, prize: str, giveaway_url: str):
    """Queue an embed when a giveaway is launched."""
    embed_data = {
        "title": f"Giveaway Started: {title}",
        "description": (
            f"**Prize:** {prize}\n\n"
            f"[Enter the Giveaway]({giveaway_url})"
        ),
        "url": giveaway_url,
        "footer": "Good luck! | casual-heroes.com/ql/giveaways/",
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
        'footer': 'QuestLog Live - casual-heroes.com/ql/',
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
        "footer": "QuestLog Giveaways | casual-heroes.com/ql/giveaways/",
    }
    _queue_notification("giveaway_winner", embed_data, GOLD_COLOR)
