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


# ---------------------------------------------------------------------------
# Public API - call these from views
# ---------------------------------------------------------------------------

def notify_lfg_post(creator: str, game_name: str, title: str, description: str,
                    group_size: int, current_size: int, scheduled_time,
                    lfg_url: str, game_image_url: str | None = None):
    """Queue a rich embed when a new LFG group is posted on QuestLog."""
    desc_preview = description[:300] + '...' if description and len(description) > 300 else (description or '')

    fields = [
        {"name": "Game",       "value": game_name,    "inline": True},
        {"name": "Group Size", "value": f"{current_size}/{group_size}", "inline": True},
    ]
    if scheduled_time:
        try:
            dt = datetime.fromtimestamp(int(scheduled_time), tz=timezone.utc)
            time_str = dt.strftime("%a, %b %-d at %-I:%M %p UTC")
        except (ValueError, TypeError, OSError):
            time_str = str(scheduled_time)
        fields.append({"name": "Scheduled", "value": time_str, "inline": True})

    embed_data = {
        "title": f"New LFG: {title}",
        "description": desc_preview if desc_preview else f"Posted by **{creator}**",
        "url": lfg_url,
        "fields": fields,
        "footer": "QuestLog LFG - casual-heroes.com/ql/",
    }
    if game_image_url:
        embed_data["thumbnail"] = game_image_url

    _queue_notification("lfg_announce", embed_data, ORANGE_COLOR)


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
