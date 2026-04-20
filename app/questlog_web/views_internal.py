# views_internal.py - Internal API for bot <-> web platform communication
#
# These endpoints are called by the QuestLog bots (Discord + Fluxer).
# Authenticated via X-Bot-Secret header (shared secret in secrets.env).
# NOT public-facing - only called from localhost or trusted bot servers.

import json
import re
import time
import logging
import urllib.request
import urllib.error

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from sqlalchemy import text as sa_text
from app.db import get_db_session
from .models import WebCommunityBotConfig, WebLFGGroup, WebBridgeConfig, WebBridgeRelayQueue, WebBridgeMessageMap, WebBridgePendingReaction, WebBridgePendingDeletion, WebFluxerGuildRole, WebFluxerGuildSettings, WebFluxerGuildAction, WebBridgeThreadMap

logger = logging.getLogger(__name__)

# Matches Matrix user IDs like @username:server.com
_MATRIX_ID_RE = re.compile(r'@[\w.\-]+:[\w.\-]+')

# Matches raw platform mention tokens we pass through from bots
# Discord/Fluxer: <@123456789> or <@!123456789>
_DISCORD_MENTION_RE = re.compile(r'<@!?(\d+)>')


def _resolve_mentions(content: str, mentions: list, source_platform: str, target_platform: str, db) -> str:
    """
    Resolve cross-platform user mentions in a bridged message.

    mentions = list of {id: <source platform user ID>, display_name: <fallback>}

    - discord/fluxer -> matrix: <@userid> -> Matrix pill HTML if user is linked
    - matrix -> discord/fluxer: @user:server -> <@discord_id> or <@fluxer_id> if linked
    - Falls back to @DisplayName text if user not linked
    """
    if not content:
        return content

    if source_platform in ('discord', 'fluxer') and target_platform == 'matrix':
        # Build lookup: source_id -> {matrix_id, display_name}
        if not mentions:
            return content
        id_map = {str(m['id']): m for m in mentions if m.get('id')}
        if not id_map:
            return content

        # Fetch matrix_ids for all mentioned users in one query
        _PLATFORM_ID_COL = {'discord': 'discord_id', 'fluxer': 'fluxer_id'}
        id_field = _PLATFORM_ID_COL.get(source_platform)
        if not id_field:
            return content
        ids = list(id_map.keys())
        placeholders = ','.join([':id' + str(i) for i in range(len(ids))])
        params = {'id' + str(i): ids[i] for i in range(len(ids))}
        # Column name comes from allowlist - not user input
        if id_field == 'discord_id':
            sql = sa_text(f"SELECT discord_id, matrix_id, username FROM web_users WHERE discord_id IN ({placeholders})")
        else:
            sql = sa_text(f"SELECT fluxer_id, matrix_id, username FROM web_users WHERE fluxer_id IN ({placeholders})")
        rows = db.execute(sql, params).fetchall()
        matrix_map = {str(r[0]): (r[1], r[2]) for r in rows}  # source_id -> (matrix_id, username)

        def replace_mention(m):
            uid = m.group(1)
            info = id_map.get(uid, {})
            display = info.get('display_name', uid)
            if uid in matrix_map:
                matrix_id, username = matrix_map[uid]
                if matrix_id:
                    # Matrix pill: <a href="https://matrix.to/#/@user:server">DisplayName</a>
                    return f'<a href="https://matrix.to/#/{matrix_id}">{display}</a>'
            return f'@{display}'

        return _DISCORD_MENTION_RE.sub(replace_mention, content)

    elif source_platform in ('discord', 'fluxer') and target_platform in ('discord', 'fluxer') and source_platform != target_platform:
        # Cross-platform between Discord and Fluxer: swap user IDs
        if not mentions:
            return content
        id_map = {str(m['id']): m for m in mentions if m.get('id')}
        if not id_map:
            return content

        ids = list(id_map.keys())
        placeholders = ','.join([':id' + str(i) for i in range(len(ids))])
        params = {'id' + str(i): ids[i] for i in range(len(ids))}
        # Column names are determined by platform logic, not user input
        if source_platform == 'discord':
            sql = sa_text(f"SELECT discord_id, fluxer_id, username FROM web_users WHERE discord_id IN ({placeholders})")
        else:
            sql = sa_text(f"SELECT fluxer_id, discord_id, username FROM web_users WHERE fluxer_id IN ({placeholders})")
        rows = db.execute(sql, params).fetchall()
        swap_map = {str(r[0]): str(r[1]) if r[1] else None for r in rows}  # src_id -> tgt_id

        def replace_cross_mention(m):
            uid = m.group(1)
            tgt_id = swap_map.get(uid)
            if tgt_id:
                return f'<@{tgt_id}>'
            # Fallback: use display name from mentions list
            info = id_map.get(uid, {})
            display = info.get('display_name', uid)
            return f'@{display}'

        return _DISCORD_MENTION_RE.sub(replace_cross_mention, content)

    elif source_platform == 'matrix' and target_platform in ('discord', 'fluxer'):
        # Find all @user:server patterns and look up platform IDs
        matrix_ids_raw = list(set(_MATRIX_ID_RE.findall(content)))
        if not matrix_ids_raw:
            return content

        # Lowercase for case-insensitive lookup (Matrix IDs are lowercase in DB)
        matrix_ids = [mid.lower() for mid in matrix_ids_raw]
        # Map lowercase -> original so we can do string replacement on original content
        lower_to_raw = {mid.lower(): mid for mid in matrix_ids_raw}

        placeholders = ','.join([':mid' + str(i) for i in range(len(matrix_ids))])
        params = {'mid' + str(i): matrix_ids[i] for i in range(len(matrix_ids))}
        # Column name determined by platform logic, not user input
        if target_platform == 'discord':
            sql = sa_text(f"SELECT matrix_id, discord_id, username FROM web_users WHERE LOWER(matrix_id) IN ({placeholders})")
        else:
            sql = sa_text(f"SELECT matrix_id, fluxer_id, username FROM web_users WHERE LOWER(matrix_id) IN ({placeholders})")
        rows = db.execute(sql, params).fetchall()
        lookup = {r[0].lower(): (r[1], r[2]) for r in rows}  # lowercase matrix_id -> (platform_id, username)

        def replace_matrix_mention(matrix_id_lower, original):
            if matrix_id_lower in lookup:
                platform_id, username = lookup[matrix_id_lower]
                if platform_id:
                    return f'<@{platform_id}>'
            # Fallback: use localpart as display name
            localpart = original.split(':')[0].lstrip('@')
            return f'@{localpart}'

        for lower_id in matrix_ids:
            original = lower_to_raw[lower_id]
            replacement = replace_matrix_mention(lower_id, original)
            # Replace case-insensitively in content (body may have mixed case)
            content = re.sub(re.escape(original), replacement, content, flags=re.IGNORECASE)
        return content

    return content


_INTERNAL_ALLOWED_IPS = {'127.0.0.1', '::1', ''}  # '' = Unix socket (always local)

def _check_bot_auth(request) -> bool:
    """Verify the request comes from the bot: local connection + shared secret (constant-time comparison).
    REMOTE_ADDR is '' for Unix socket connections (nginx -> gunicorn via socket) and '127.0.0.1' for TCP.
    Both are local-only - no external IP can arrive with an empty REMOTE_ADDR via a Unix socket.
    """
    import hmac
    # Restrict to localhost connections only
    remote_ip = request.META.get('REMOTE_ADDR', '')
    if remote_ip not in _INTERNAL_ALLOWED_IPS:
        logger.warning(f"Internal API rejected non-local IP: {remote_ip}")
        return False
    secret = getattr(settings, 'BOT_INTERNAL_SECRET', '')
    if not secret:
        logger.warning("BOT_INTERNAL_SECRET not configured - internal API disabled")
        return False
    provided = request.META.get('HTTP_X_BOT_SECRET', '')
    return hmac.compare_digest(provided, secret)


def _config_dict(cfg: WebCommunityBotConfig) -> dict:
    return {
        'id': cfg.id,
        'community_id': cfg.community_id,
        'platform': cfg.platform,
        'guild_id': cfg.guild_id,
        'guild_name': cfg.guild_name,
        'channel_id': cfg.channel_id,
        'channel_name': cfg.channel_name,
        'event_type': cfg.event_type,
        'is_enabled': cfg.is_enabled,
    }


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_internal_bot_config(request):
    """
    GET  ?platform=fluxer&guild_id=123 - fetch configs for a guild
    POST - register or update a channel subscription (called by !setup command)
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if request.method == 'GET':
        platform = request.GET.get('platform', '').strip()
        guild_id = request.GET.get('guild_id', '').strip()
        if not platform or not guild_id:
            return JsonResponse({'error': 'platform and guild_id required'}, status=400)

        with get_db_session() as db:
            configs = db.query(WebCommunityBotConfig).filter_by(
                platform=platform, guild_id=guild_id
            ).all()
            return JsonResponse({'configs': [_config_dict(c) for c in configs]})

    # POST - register/update subscription
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    platform = data.get('platform', '').strip()
    guild_id = data.get('guild_id', '').strip()
    event_type = data.get('event_type', '').strip()

    if not all([platform, guild_id, event_type]):
        return JsonResponse({'error': 'platform, guild_id, event_type required'}, status=400)

    # Only allow known platforms and event types
    if platform not in ('discord', 'fluxer'):
        return JsonResponse({'error': 'Invalid platform'}, status=400)
    if event_type not in ('lfg_announce',):
        return JsonResponse({'error': 'Invalid event_type'}, status=400)

    # Validate webhook_url if provided - must be HTTPS and a known Discord/Fluxer webhook host
    webhook_url = data.get('webhook_url') or ''
    if webhook_url:
        from urllib.parse import urlparse
        _wh = urlparse(webhook_url)
        _allowed_wh_hosts = {'discord.com', 'discordapp.com', 'fluxer.net'}
        if _wh.scheme != 'https' or _wh.netloc not in _allowed_wh_hosts:
            return JsonResponse({'error': 'Invalid webhook_url'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        cfg = db.query(WebCommunityBotConfig).filter_by(
            platform=platform, guild_id=guild_id, event_type=event_type
        ).first()

        if cfg:
            cfg.channel_id = data.get('channel_id') or cfg.channel_id
            cfg.channel_name = data.get('channel_name') or cfg.channel_name
            cfg.webhook_url = data.get('webhook_url') or cfg.webhook_url
            cfg.guild_name = data.get('guild_name') or cfg.guild_name
            cfg.is_enabled = True
            cfg.updated_at = now
        else:
            cfg = WebCommunityBotConfig(
                platform=platform,
                guild_id=guild_id,
                guild_name=data.get('guild_name'),
                channel_id=data.get('channel_id'),
                channel_name=data.get('channel_name'),
                webhook_url=data.get('webhook_url'),
                event_type=event_type,
                is_enabled=True,
                created_at=now,
                updated_at=now,
            )
            db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return JsonResponse({'success': True, 'config': _config_dict(cfg)}, status=201)


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_broadcast_lfg(request, lfg_id):
    """
    POST /api/internal/lfg/<id>/broadcast/
    Called by the web platform when user clicks "Broadcast to Network".
    Fires the LFG embed to all opted-in communities.
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    import requests as _req

    with get_db_session() as db:
        lfg = db.query(WebLFGGroup).filter_by(id=lfg_id).first()
        if not lfg:
            return JsonResponse({'error': 'LFG not found'}, status=404)

        # Get all enabled lfg_announce webhook URLs
        configs = db.query(WebCommunityBotConfig).filter_by(
            event_type='lfg_announce', is_enabled=True
        ).filter(WebCommunityBotConfig.webhook_url.isnot(None)).all()

        webhook_urls = [c.webhook_url for c in configs]
        lfg_data = {
            'title': lfg.title,
            'game': lfg.game_name,
            'description': lfg.description or '',
            'group_size': lfg.group_size,
            'current_size': lfg.current_size,
            'voice_platform': lfg.voice_platform or '',
            'game_image_url': lfg.game_image_url or '',
        }

    if not webhook_urls:
        return JsonResponse({'success': True, 'sent': 0, 'message': 'No subscribed communities'})

    # Build the embed
    desc_parts = []
    if lfg_data['description']:
        desc_parts.append(lfg_data['description'])
    desc_parts.append(f"\n[Join on QuestLog](https://casual-heroes.com/ql/lfg/)")

    embed = {
        "title": f"LFG - {lfg_data['game']}: {lfg_data['title']}",
        "description": "\n".join(desc_parts),
        "url": "https://casual-heroes.com/ql/lfg/",
        "color": 0xFEE75C,
        "fields": [
            {"name": "Game", "value": lfg_data['game'], "inline": True},
            {"name": "Group Size", "value": f"{lfg_data['current_size']}/{lfg_data['group_size']}", "inline": True},
        ],
        "footer": {"text": "QuestLog Network | casual-heroes.com/ql/lfg/"},
    }
    if lfg_data['voice_platform']:
        embed["fields"].append({"name": "Voice", "value": lfg_data['voice_platform'].title(), "inline": True})
    if lfg_data['game_image_url']:
        embed["thumbnail"] = {"url": lfg_data['game_image_url']}

    payload = {"username": "QuestLog Network", "embeds": [embed]}

    sent = 0
    import threading

    def fire(url):
        nonlocal sent
        try:
            r = _req.post(url, json=payload, timeout=6)
            if r.status_code in (200, 204):
                sent += 1
        except Exception as e:
            logger.warning(f"Network LFG broadcast failed for {url[:50]}: {e}")

    threads = [threading.Thread(target=fire, args=(url,), daemon=True) for url in webhook_urls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=8)

    return JsonResponse({'success': True, 'sent': sent, 'total': len(webhook_urls)})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_guild_names(request):
    """
    POST /ql/internal/guild-names/
    Called by the Fluxer bot on startup (on_ready) with the list of guilds it is in.
    Updates guild_name in web_fluxer_guild_channels so the admin UI can show names.

    Body: {"guilds": [{"id": "123456", "name": "Casual Heroes"}, ...]}
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    guilds = data.get('guilds', [])
    if not isinstance(guilds, list):
        return JsonResponse({'error': 'guilds must be a list'}, status=400)

    updated = 0
    with get_db_session() as db:
        for g in guilds:
            guild_id = str(g.get('id', '')).strip()
            guild_name = str(g.get('name', '')).strip()
            if not guild_id or not guild_name:
                continue
            # Update channel table
            result = db.execute(sa_text(
                "UPDATE web_fluxer_guild_channels "
                "SET guild_name = :name "
                "WHERE guild_id = :gid AND (guild_name = '' OR guild_name IS NULL OR guild_name != :name)"
            ), {'name': guild_name, 'gid': guild_id})
            updated += result.rowcount
            # Also update settings table if a row exists (bot owns the guild_name field)
            db.execute(sa_text(
                "UPDATE web_fluxer_guild_settings "
                "SET guild_name = :name "
                "WHERE guild_id = :gid AND (guild_name = '' OR guild_name IS NULL OR guild_name != :name)"
            ), {'name': guild_name, 'gid': guild_id})
        db.commit()

    logger.info(f'api_internal_guild_names: updated {updated} rows for {len(guilds)} guilds')
    return JsonResponse({'success': True, 'updated': updated})


# =============================================================================
# BRIDGE RELAY (chat message relay between Discord and Fluxer)
# =============================================================================

@csrf_exempt
@require_http_methods(['POST'])
def api_internal_bridge_relay(request):
    """
    POST /ql/internal/bridge/relay/
    Called by either bot when a bridged channel receives a message.

    Body: {
        "discord_channel_id": "...",   // OR "fluxer_channel_id"
        "source_platform": "discord",  // or "fluxer"
        "author_name": "Username",
        "author_avatar": "https://...",  // optional
        "content": "Message text"
    }

    Anti-loop: bots must NOT call this for messages they sent themselves
    (check author.id != bot.user.id before calling).
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    source_platform = data.get('source_platform', '').strip()
    author_name = str(data.get('author_name', 'Unknown'))[:80]
    author_avatar = data.get('author_avatar') or None
    if author_avatar:
        _allowed_avatar_prefixes = (
            'https://cdn.discordapp.com/',
            'https://fluxerusercontent.com/',
            'https://avatars.githubusercontent.com/',
            'https://media.discordapp.net/',
        )
        if not any(author_avatar.startswith(p) for p in _allowed_avatar_prefixes):
            author_avatar = None
    content = str(data.get('content', '')).strip()
    source_message_id = str(data.get('source_message_id', '') or '')[:255] or None
    reply_quote = str(data.get('reply_quote', '') or '')[:200] or None
    reply_to_message_id = str(data.get('reply_to_message_id', '') or '')[:255] or None

    # Mentions: list of {id, display_name} with source-platform native user IDs
    raw_mentions = data.get('mentions') or []
    mentions = []
    if isinstance(raw_mentions, list):
        for m in raw_mentions[:50]:
            if isinstance(m, dict) and m.get('id'):
                mentions.append({
                    'id': str(m['id'])[:64],
                    'display_name': str(m.get('display_name', '') or '')[:80],
                })
    mentions_json_str = json.dumps(mentions) if mentions else None

    # Attachments: list of {url, filename, content_type} - URLs must be https
    raw_attachments = data.get('attachments') or []
    attachments = []
    if isinstance(raw_attachments, list):
        for att in raw_attachments[:10]:
            if not isinstance(att, dict):
                continue
            url = str(att.get('url', '') or '').strip()[:500]
            if not url.startswith('https://'):
                continue
            discord_url = str(att.get('discord_url', '') or '').strip()[:500]
            entry = {
                'url': url,
                'filename': str(att.get('filename', '') or '')[:200],
                'content_type': str(att.get('content_type', '') or '')[:50],
            }
            if discord_url.startswith('https://'):
                entry['discord_url'] = discord_url
            attachments.append(entry)

    if source_platform not in ('discord', 'fluxer', 'matrix'):
        return JsonResponse({'error': 'source_platform must be discord, fluxer, or matrix'}, status=400)
    if not content and not attachments:
        return JsonResponse({'error': 'content or attachments required'}, status=400)

    attachments_json_str = json.dumps(attachments) if attachments else None

    # Thread ID: source platform's thread channel ID (Discord) or root event ID (Matrix)
    thread_id = str(data.get('thread_id', '') or '')[:255] or None

    now = int(time.time())

    # Find bridge config by source channel, then queue to all other platforms in the bridge
    if source_platform == 'discord':
        channel_id = str(data.get('discord_channel_id', '')).strip()
        if not channel_id:
            return JsonResponse({'error': 'discord_channel_id required'}, status=400)
        with get_db_session() as db:
            bridge = db.query(WebBridgeConfig).filter_by(
                discord_channel_id=channel_id, enabled=1
            ).first()
            if not bridge or not bridge.relay_discord_to_fluxer:
                return JsonResponse({'queued': 0, 'reason': 'No active bridge for this channel'})

            max_len = bridge.max_msg_len
            if len(content) > max_len:
                content = content[:max_len - 3] + '...'

            queued = 0
            relay_row_ids = []
            # -> Fluxer
            if bridge.fluxer_channel_id and bridge.relay_discord_to_fluxer:
                row = WebBridgeRelayQueue(
                    bridge_id=bridge.id, source_platform='discord',
                    source_message_id=source_message_id,
                    author_name=author_name, author_avatar=author_avatar,
                    content=content, reply_quote=reply_quote,
                    reply_to_source_message_id=reply_to_message_id,
                    attachments_json=attachments_json_str,
                    mentions_json=mentions_json_str,
                    thread_id=thread_id,
                    target_platform='fluxer', target_channel_id=bridge.fluxer_channel_id,
                    created_at=now,
                )
                db.add(row)
                db.flush()
                relay_row_ids.append(row.id)
                queued += 1
            # -> Matrix
            if bridge.matrix_room_id and getattr(bridge, 'relay_matrix_inbound', 1):
                row = WebBridgeRelayQueue(
                    bridge_id=bridge.id, source_platform='discord',
                    source_message_id=source_message_id,
                    author_name=author_name, author_avatar=author_avatar,
                    content=content, reply_quote=reply_quote,
                    reply_to_source_message_id=reply_to_message_id,
                    attachments_json=attachments_json_str,
                    mentions_json=mentions_json_str,
                    thread_id=thread_id,
                    target_platform='matrix', target_channel_id=bridge.matrix_room_id,
                    created_at=now,
                )
                db.add(row)
                db.flush()
                relay_row_ids.append(row.id)
                queued += 1
            # Record source message in map for every relay row so cross-platform reply
            # lookup works regardless of which row the target bot stores its delivery under
            if source_message_id:
                for rid in relay_row_ids:
                    db.add(WebBridgeMessageMap(
                        relay_queue_id=rid, platform='discord',
                        message_id=source_message_id, channel_id=channel_id, created_at=now,
                    ))
            db.commit()
        return JsonResponse({'queued': queued})

    elif source_platform == 'fluxer':
        channel_id = str(data.get('fluxer_channel_id', '')).strip()
        if not channel_id:
            return JsonResponse({'error': 'fluxer_channel_id required'}, status=400)
        with get_db_session() as db:
            bridge = db.query(WebBridgeConfig).filter_by(
                fluxer_channel_id=channel_id, enabled=1
            ).first()
            if not bridge or not bridge.relay_fluxer_to_discord:
                return JsonResponse({'queued': 0, 'reason': 'No active bridge for this channel'})

            max_len = bridge.max_msg_len
            if len(content) > max_len:
                content = content[:max_len - 3] + '...'

            queued = 0
            relay_row_ids = []
            # -> Discord
            if bridge.discord_channel_id and bridge.relay_fluxer_to_discord:
                row = WebBridgeRelayQueue(
                    bridge_id=bridge.id, source_platform='fluxer',
                    source_message_id=source_message_id,
                    author_name=author_name, author_avatar=author_avatar,
                    content=content, reply_quote=reply_quote,
                    reply_to_source_message_id=reply_to_message_id,
                    attachments_json=attachments_json_str,
                    mentions_json=mentions_json_str,
                    thread_id=thread_id,
                    target_platform='discord', target_channel_id=bridge.discord_channel_id,
                    created_at=now,
                )
                db.add(row)
                db.flush()
                relay_row_ids.append(row.id)
                queued += 1
            # -> Matrix
            if bridge.matrix_room_id and getattr(bridge, 'relay_matrix_inbound', 1):
                row = WebBridgeRelayQueue(
                    bridge_id=bridge.id, source_platform='fluxer',
                    source_message_id=source_message_id,
                    author_name=author_name, author_avatar=author_avatar,
                    content=content, reply_quote=reply_quote,
                    reply_to_source_message_id=reply_to_message_id,
                    attachments_json=attachments_json_str,
                    mentions_json=mentions_json_str,
                    thread_id=thread_id,
                    target_platform='matrix', target_channel_id=bridge.matrix_room_id,
                    created_at=now,
                )
                db.add(row)
                db.flush()
                relay_row_ids.append(row.id)
                queued += 1
            if source_message_id:
                for rid in relay_row_ids:
                    db.add(WebBridgeMessageMap(
                        relay_queue_id=rid, platform='fluxer',
                        message_id=source_message_id, channel_id=channel_id, created_at=now,
                    ))
            db.commit()
        return JsonResponse({'queued': queued})

    else:  # matrix
        room_id = str(data.get('matrix_room_id', '')).strip()
        if not room_id:
            return JsonResponse({'error': 'matrix_room_id required'}, status=400)
        with get_db_session() as db:
            bridge = db.query(WebBridgeConfig).filter_by(
                matrix_room_id=room_id, enabled=1
            ).first()
            if not bridge or not getattr(bridge, 'relay_matrix_outbound', 1):
                return JsonResponse({'queued': 0, 'reason': 'No active bridge for this room'})

            max_len = bridge.max_msg_len
            if len(content) > max_len:
                content = content[:max_len - 3] + '...'

            queued = 0
            relay_row_ids = []
            # -> Discord
            if bridge.discord_channel_id:
                row = WebBridgeRelayQueue(
                    bridge_id=bridge.id, source_platform='matrix',
                    source_message_id=source_message_id,
                    author_name=author_name, author_avatar=author_avatar,
                    content=content, reply_quote=reply_quote,
                    reply_to_source_message_id=reply_to_message_id,
                    attachments_json=attachments_json_str,
                    mentions_json=mentions_json_str,
                    thread_id=thread_id,
                    target_platform='discord', target_channel_id=bridge.discord_channel_id,
                    created_at=now,
                )
                db.add(row)
                db.flush()
                relay_row_ids.append(row.id)
                queued += 1
            # -> Fluxer
            if bridge.fluxer_channel_id:
                row = WebBridgeRelayQueue(
                    bridge_id=bridge.id, source_platform='matrix',
                    source_message_id=source_message_id,
                    author_name=author_name, author_avatar=author_avatar,
                    content=content, reply_quote=reply_quote,
                    reply_to_source_message_id=reply_to_message_id,
                    attachments_json=attachments_json_str,
                    mentions_json=mentions_json_str,
                    thread_id=thread_id,
                    target_platform='fluxer', target_channel_id=bridge.fluxer_channel_id,
                    created_at=now,
                )
                db.add(row)
                db.flush()
                relay_row_ids.append(row.id)
                queued += 1
            if source_message_id:
                for rid in relay_row_ids:
                    db.add(WebBridgeMessageMap(
                        relay_queue_id=rid, platform='matrix',
                        message_id=source_message_id, channel_id=room_id, created_at=now,
                    ))
            db.commit()
        return JsonResponse({'queued': queued})


@csrf_exempt
@require_http_methods(['GET'])
def api_internal_bridge_pending(request, platform):
    """
    GET /ql/internal/bridge/pending/<platform>/
    Called by bots every 3s to pick up messages to relay to their platform.
    Returns up to 20 undelivered messages and marks them delivered.

    platform = 'discord' or 'fluxer'
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if platform not in ('discord', 'fluxer', 'matrix'):
        return JsonResponse({'error': 'Invalid platform'}, status=400)

    now = int(time.time())
    # Only return messages created in the last 5 minutes (avoid stale replay)
    cutoff = now - 300

    with get_db_session() as db:
        rows = (
            db.query(WebBridgeRelayQueue)
            .filter(
                WebBridgeRelayQueue.target_platform == platform,
                WebBridgeRelayQueue.delivered_at == None,
                WebBridgeRelayQueue.created_at >= cutoff,
            )
            .order_by(WebBridgeRelayQueue.created_at)
            .limit(20)
            .all()
        )

        if not rows:
            return JsonResponse({'messages': []})

        ids = [r.id for r in rows]

        # For each row that is a reply, look up the target-platform event ID
        # so the receiving bot can create a proper threaded reply.
        #
        # The reply_to_source_message_id is the message ID on the ORIGINATING platform
        # (e.g. a Matrix event ID if the original came from Matrix, a Discord message ID
        # if it came from Discord, etc.).
        #
        # Strategy:
        # 1. Direct: find a map entry where message_id=reply_to AND platform=target_platform
        #    (works when the target platform was also the source of the original message)
        # 2. Via source map entry: find ANY map entry for that message_id, get its
        #    relay_queue_id, find the sibling relay queue row that targeted our platform,
        #    then look up that row's delivery in the map.
        reply_event_ids = {}
        reply_rows = [r for r in rows if r.reply_to_source_message_id]
        if reply_rows:
            for r in reply_rows:
                # Step 1: direct lookup (e.g. replying to a message that originated on target platform)
                tgt_map = db.query(WebBridgeMessageMap).filter_by(
                    platform=platform,
                    message_id=r.reply_to_source_message_id,
                ).first()
                if tgt_map:
                    reply_event_ids[r.id] = tgt_map.message_id
                    continue

                # Step 2: find any map entry for the replied-to message ID
                any_map = db.query(WebBridgeMessageMap).filter(
                    WebBridgeMessageMap.message_id == r.reply_to_source_message_id,
                ).first()
                if not any_map:
                    continue

                # Find the relay queue row that corresponds to that map entry
                origin_row = db.query(WebBridgeRelayQueue).filter_by(
                    id=any_map.relay_queue_id,
                ).first()
                if not origin_row:
                    continue

                # If the original message came FROM our target platform, its
                # source_message_id IS the native message ID we need - no sibling lookup required
                if origin_row.source_platform == platform and origin_row.source_message_id:
                    reply_event_ids[r.id] = origin_row.source_message_id
                    continue

                # Find the sibling relay row that targeted our platform
                # (same bridge, same source_message_id, same source_platform)
                sibling = db.query(WebBridgeRelayQueue).filter_by(
                    bridge_id=origin_row.bridge_id,
                    source_platform=origin_row.source_platform,
                    source_message_id=origin_row.source_message_id,
                    target_platform=platform,
                ).first()
                if not sibling:
                    continue

                # Find the delivery record for that sibling row
                sibling_map = db.query(WebBridgeMessageMap).filter_by(
                    relay_queue_id=sibling.id,
                    platform=platform,
                ).first()
                if sibling_map:
                    reply_event_ids[r.id] = sibling_map.message_id

        # Pre-resolve thread root event IDs to target-platform message IDs
        # (same logic as reply_event_ids but for thread_id field)
        thread_root_event_ids = {}
        thread_rows = [r for r in rows if r.thread_id]
        for r in thread_rows:
            # Find the delivery of the thread root on the target platform
            tgt_map = db.query(WebBridgeMessageMap).filter_by(
                platform=platform,
                message_id=r.thread_id,
            ).first()
            if tgt_map:
                thread_root_event_ids[r.id] = tgt_map.message_id
                continue
            # Via relay row lookup
            any_map = db.query(WebBridgeMessageMap).filter_by(
                message_id=r.thread_id,
            ).first()
            if not any_map:
                continue
            origin_row = db.query(WebBridgeRelayQueue).filter_by(id=any_map.relay_queue_id).first()
            if not origin_row:
                continue
            if origin_row.source_platform == platform and origin_row.source_message_id:
                thread_root_event_ids[r.id] = origin_row.source_message_id
                continue
            sibling = db.query(WebBridgeRelayQueue).filter_by(
                bridge_id=origin_row.bridge_id,
                source_platform=origin_row.source_platform,
                source_message_id=origin_row.source_message_id,
                target_platform=platform,
            ).first()
            if sibling:
                sibling_map = db.query(WebBridgeMessageMap).filter_by(
                    relay_queue_id=sibling.id, platform=platform,
                ).first()
                if sibling_map:
                    thread_root_event_ids[r.id] = sibling_map.message_id

        messages = []
        for r in rows:
            mentions = json.loads(r.mentions_json) if r.mentions_json else []
            content = _resolve_mentions(r.content, mentions, r.source_platform, platform, db)

            # Thread resolution: look up mapped thread ID on target platform
            target_thread_id = None
            source_thread_id = r.thread_id

            if source_thread_id:
                tmap = None
                if r.source_platform == 'discord':
                    tmap = db.query(WebBridgeThreadMap).filter_by(
                        bridge_id=r.bridge_id, discord_thread_id=source_thread_id
                    ).first()
                    if tmap and platform == 'matrix':
                        target_thread_id = tmap.matrix_thread_event_id
                elif r.source_platform == 'matrix':
                    tmap = db.query(WebBridgeThreadMap).filter_by(
                        bridge_id=r.bridge_id, matrix_thread_event_id=source_thread_id
                    ).first()
                    if tmap and platform == 'discord':
                        target_thread_id = tmap.discord_thread_id

            # No explicit thread_id: check if this is a reply to a message that has a thread.
            # Covers Fluxer (or any platform) replying to a bridged message that's part of a thread.
            if not source_thread_id and r.reply_to_source_message_id and platform in ('discord', 'matrix'):
                # Step 1: find relay row via message_map (handles cross-platform relay IDs)
                replied_map = db.query(WebBridgeMessageMap).filter_by(
                    message_id=r.reply_to_source_message_id,
                ).first()
                replied_relay_id = replied_map.relay_queue_id if replied_map else None

                # Fallback: try direct source_message_id match (same-platform case)
                if not replied_relay_id:
                    replied_relay = db.query(WebBridgeRelayQueue).filter_by(
                        bridge_id=r.bridge_id,
                        source_message_id=r.reply_to_source_message_id,
                    ).first()
                    replied_relay_id = replied_relay.id if replied_relay else None

                if replied_relay_id:
                    if platform == 'discord':
                        # Find the Discord delivery and look up by discord_parent_message_id
                        plat_map = db.query(WebBridgeMessageMap).filter_by(
                            relay_queue_id=replied_relay_id, platform='discord'
                        ).first()
                        tmap = None
                        if plat_map:
                            tmap = db.query(WebBridgeThreadMap).filter_by(
                                bridge_id=r.bridge_id,
                                discord_parent_message_id=plat_map.message_id,
                            ).first()
                        if tmap and tmap.discord_thread_id:
                            source_thread_id = tmap.discord_thread_id
                            target_thread_id = tmap.discord_thread_id
                        else:
                            # Fallback: the replied-to relay row may have thread_id = Matrix root event ID
                            # (for Matrix-originated threads where discord_parent_message_id is NULL)
                            replied_relay_row = db.query(WebBridgeRelayQueue).filter_by(
                                id=replied_relay_id
                            ).first()
                            if replied_relay_row and replied_relay_row.thread_id:
                                tmap2 = db.query(WebBridgeThreadMap).filter_by(
                                    bridge_id=r.bridge_id,
                                    matrix_thread_event_id=replied_relay_row.thread_id,
                                ).first()
                                if tmap2 and tmap2.discord_thread_id:
                                    source_thread_id = tmap2.discord_thread_id
                                    target_thread_id = tmap2.discord_thread_id
                            elif replied_relay_row and replied_relay_row.source_platform == 'matrix':
                                # The replied-to message itself might be the Matrix thread root
                                tmap2 = db.query(WebBridgeThreadMap).filter_by(
                                    bridge_id=r.bridge_id,
                                    matrix_thread_event_id=replied_relay_row.source_message_id,
                                ).first()
                                if tmap2 and tmap2.discord_thread_id:
                                    source_thread_id = tmap2.discord_thread_id
                                    target_thread_id = tmap2.discord_thread_id

                    elif platform == 'matrix':
                        # Get the relay row for the replied-to message to find its thread_id
                        replied_relay_row = db.query(WebBridgeRelayQueue).filter_by(
                            id=replied_relay_id
                        ).first()
                        matrix_thread_root = None
                        if replied_relay_row and replied_relay_row.thread_id:
                            # The replied-to message was in a thread - look up the Matrix root
                            tmap = db.query(WebBridgeThreadMap).filter_by(
                                bridge_id=r.bridge_id,
                                discord_thread_id=replied_relay_row.thread_id,
                            ).first()
                            if tmap and tmap.matrix_thread_event_id:
                                matrix_thread_root = tmap.matrix_thread_event_id
                        else:
                            # The replied-to message may itself be the thread root on Discord
                            discord_map = db.query(WebBridgeMessageMap).filter_by(
                                relay_queue_id=replied_relay_id, platform='discord'
                            ).first()
                            if discord_map:
                                tmap = db.query(WebBridgeThreadMap).filter_by(
                                    bridge_id=r.bridge_id,
                                    discord_parent_message_id=discord_map.message_id,
                                ).first()
                                if tmap and tmap.matrix_thread_event_id:
                                    matrix_thread_root = tmap.matrix_thread_event_id
                        if matrix_thread_root:
                            source_thread_id = matrix_thread_root
                            target_thread_id = matrix_thread_root

            messages.append({
                'id': r.id,
                'bridge_id': r.bridge_id,
                'source_platform': r.source_platform,
                'author_name': r.author_name,
                'author_avatar': r.author_avatar,
                'content': content,
                'reply_quote': r.reply_quote,
                'reply_to_event_id': reply_event_ids.get(r.id),
                'thread_root_event_id': thread_root_event_ids.get(r.id),  # target-platform ID of the thread root
                'attachments': json.loads(r.attachments_json) if r.attachments_json else [],
                'target_channel_id': r.target_channel_id,
                'source_thread_id': source_thread_id,  # source platform thread ID (for creating new map)
                'target_thread_id': target_thread_id,  # target platform thread ID if already mapped
            })

        # Mark delivered
        db.query(WebBridgeRelayQueue).filter(
            WebBridgeRelayQueue.id.in_(ids)
        ).update({'delivered_at': now}, synchronize_session=False)
        db.commit()

    return JsonResponse({'messages': messages})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_bridge_message_map(request):
    """
    POST /ql/internal/bridge/message-map/
    Called by a bot after it successfully delivers a relayed message.
    Records the sent message ID so reactions can be mapped cross-platform.

    Body: {
        "relay_queue_id": 123,
        "platform": "discord",    // platform the message was delivered TO
        "message_id": "987654",   // ID of the sent message on that platform
        "channel_id": "111222"    // channel it was sent to
    }
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    relay_queue_id = data.get('relay_queue_id')
    platform = (data.get('platform') or '').strip()
    message_id = str(data.get('message_id', '') or '')[:255]
    channel_id = str(data.get('channel_id', '') or '')[:255]

    if not relay_queue_id or platform not in ('discord', 'fluxer', 'matrix') or not message_id or not channel_id:
        return JsonResponse({'error': 'relay_queue_id, platform, message_id, channel_id required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        # Avoid duplicates
        existing = db.query(WebBridgeMessageMap).filter_by(
            relay_queue_id=relay_queue_id, platform=platform
        ).first()
        if not existing:
            db.add(WebBridgeMessageMap(
                relay_queue_id=relay_queue_id,
                platform=platform,
                message_id=message_id,
                channel_id=channel_id,
                created_at=now,
            ))
            db.commit()

    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_bridge_thread_map(request):
    """
    POST /ql/internal/bridge/thread-map/
    Called by a bot after it creates a thread on the target platform.
    Records the mapping so future messages in the same thread go to the right place.

    Body: {
        "bridge_id": 1,
        "discord_thread_id": "...",      // Discord thread channel ID (omit if Matrix-sourced)
        "matrix_thread_event_id": "..."  // Matrix root event ID (omit if Discord-sourced)
    }
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    bridge_id = data.get('bridge_id')
    discord_thread_id = str(data.get('discord_thread_id', '') or '')[:255] or None
    discord_parent_message_id = str(data.get('discord_parent_message_id', '') or '')[:255] or None
    matrix_thread_event_id = str(data.get('matrix_thread_event_id', '') or '')[:255] or None

    if not bridge_id or not (discord_thread_id or matrix_thread_event_id):
        return JsonResponse({'error': 'bridge_id and at least one thread ID required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        # Look for existing entry to update rather than duplicate
        existing = None
        if discord_thread_id:
            existing = db.query(WebBridgeThreadMap).filter_by(
                bridge_id=bridge_id, discord_thread_id=discord_thread_id
            ).first()
        elif matrix_thread_event_id:
            existing = db.query(WebBridgeThreadMap).filter_by(
                bridge_id=bridge_id, matrix_thread_event_id=matrix_thread_event_id
            ).first()

        if existing:
            if discord_thread_id:
                existing.discord_thread_id = discord_thread_id
            if discord_parent_message_id:
                existing.discord_parent_message_id = discord_parent_message_id
            if matrix_thread_event_id:
                existing.matrix_thread_event_id = matrix_thread_event_id
        else:
            db.add(WebBridgeThreadMap(
                bridge_id=bridge_id,
                discord_thread_id=discord_thread_id,
                discord_parent_message_id=discord_parent_message_id,
                matrix_thread_event_id=matrix_thread_event_id,
                created_at=now,
            ))
        db.commit()

    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_bridge_reaction(request):
    """
    POST /ql/internal/bridge/reaction/
    Called by a bot when a unicode emoji reaction is added to a bridged message.
    Looks up the cross-platform message mapping and queues a pending reaction.
    Only unicode emojis are relayed (bots should pre-filter custom emojis).

    Body: {
        "platform": "discord",        // platform where reaction was added
        "message_id": "456789",       // message that was reacted to
        "channel_id": "111222",
        "emoji": "U+1F44D"            // unicode emoji string
    }
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    platform = (data.get('platform') or '').strip()
    message_id = str(data.get('message_id', '') or '')[:255]
    emoji = str(data.get('emoji', '') or '')[:100]

    if platform not in ('discord', 'fluxer', 'matrix') or not message_id or not emoji:
        return JsonResponse({'error': 'platform, message_id, emoji required'}, status=400)

    now = int(time.time())
    # Queue reaction to all other platforms that have a mapping for this relay
    with get_db_session() as db:
        # Find ALL relay queue IDs for this source message (one per target platform)
        src_maps = db.query(WebBridgeMessageMap).filter_by(
            platform=platform, message_id=message_id
        ).all()
        if not src_maps:
            return JsonResponse({'queued': 0, 'reason': 'Message not in any bridge'})

        relay_ids = [m.relay_queue_id for m in src_maps]

        # Expand to sibling relay rows: same bridge + source_message_id but different
        # target platform. This handles the case where one source message fans out to
        # multiple target relay rows (e.g. matrix->discord AND matrix->fluxer are two
        # separate rows, but reactions on the discord delivery need to reach fluxer too).
        sibling_rows = db.query(WebBridgeRelayQueue).filter(
            WebBridgeRelayQueue.id.in_(relay_ids)
        ).all()
        if sibling_rows:
            # For each unique (bridge_id, source_message_id) combo, find all sibling rows
            for row in sibling_rows:
                if not row.source_message_id:
                    continue
                siblings = db.query(WebBridgeRelayQueue).filter_by(
                    bridge_id=row.bridge_id,
                    source_message_id=row.source_message_id,
                ).all()
                for s in siblings:
                    if s.id not in relay_ids:
                        relay_ids.append(s.id)

        # Find all other platform mappings across all relay rows for this message
        all_maps = db.query(WebBridgeMessageMap).filter(
            WebBridgeMessageMap.relay_queue_id.in_(relay_ids),
            WebBridgeMessageMap.platform != platform,
        ).all()
        if not all_maps:
            return JsonResponse({'queued': 0, 'reason': 'Target message not yet delivered'})

        queued = 0
        for tgt_map in all_maps:
            # Dedup: skip if same emoji already pending for this target message
            existing = db.query(WebBridgePendingReaction).filter_by(
                target_platform=tgt_map.platform,
                target_message_id=tgt_map.message_id,
                emoji=emoji,
                delivered_at=None,
            ).first()
            if existing:
                continue
            db.add(WebBridgePendingReaction(
                source_platform=platform,
                emoji=emoji,
                target_platform=tgt_map.platform,
                target_message_id=tgt_map.message_id,
                target_channel_id=tgt_map.channel_id,
                created_at=now,
            ))
            queued += 1
        db.commit()

    return JsonResponse({'queued': queued})


@csrf_exempt
@require_http_methods(['GET'])
def api_internal_bridge_pending_reactions(request, platform):
    """
    GET /ql/internal/bridge/pending-reactions/<platform>/
    Called by bots every 6s to pick up emoji reactions to add to messages.
    Returns up to 10 undelivered reactions and marks them delivered.

    platform = 'discord' or 'fluxer'
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if platform not in ('discord', 'fluxer', 'matrix'):
        return JsonResponse({'error': 'Invalid platform'}, status=400)

    now = int(time.time())
    cutoff = now - 300  # ignore reactions older than 5 minutes

    with get_db_session() as db:
        rows = (
            db.query(WebBridgePendingReaction)
            .filter(
                WebBridgePendingReaction.target_platform == platform,
                WebBridgePendingReaction.delivered_at == None,
                WebBridgePendingReaction.created_at >= cutoff,
            )
            .order_by(WebBridgePendingReaction.created_at)
            .limit(10)
            .all()
        )

        if not rows:
            return JsonResponse({'reactions': []})

        ids = [r.id for r in rows]
        reactions = [
            {
                'id': r.id,
                'emoji': r.emoji,
                'target_message_id': r.target_message_id,
                'target_channel_id': r.target_channel_id,
            }
            for r in rows
        ]

        db.query(WebBridgePendingReaction).filter(
            WebBridgePendingReaction.id.in_(ids)
        ).update({'delivered_at': now}, synchronize_session=False)
        db.commit()

    return JsonResponse({'reactions': reactions})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_bridge_delete(request):
    """
    POST /ql/internal/bridge/delete/
    Called by a bot when a message is deleted in a bridged channel.
    Looks up the cross-platform message map and queues a pending deletion.
    Deduped by target_message_id to prevent echo loops (bot deletes message
    on Platform B -> delete event fires -> would re-queue deletion of Platform A).

    Body: {
        "platform": "discord",
        "message_id": "456789",
        "channel_id": "111222"
    }
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    platform = (data.get('platform') or '').strip()
    message_id = str(data.get('message_id', '') or '')[:255]

    if platform not in ('discord', 'fluxer', 'matrix') or not message_id:
        return JsonResponse({'error': 'platform and message_id required'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        # Find relay_queue_id from this platform's message
        src_map = db.query(WebBridgeMessageMap).filter_by(
            platform=platform, message_id=message_id
        ).first()
        if not src_map:
            return JsonResponse({'queued': 0, 'reason': 'Message not in any bridge'})

        # Find all other platform mappings for this relay
        all_maps = db.query(WebBridgeMessageMap).filter(
            WebBridgeMessageMap.relay_queue_id == src_map.relay_queue_id,
            WebBridgeMessageMap.platform != platform,
        ).all()
        if not all_maps:
            return JsonResponse({'queued': 0, 'reason': 'Target message not yet delivered'})

        queued = 0
        for tgt_map in all_maps:
            # Dedup: skip if deletion already queued for this target message
            existing = db.query(WebBridgePendingDeletion).filter_by(
                target_platform=tgt_map.platform,
                target_message_id=tgt_map.message_id,
            ).first()
            if existing:
                continue
            db.add(WebBridgePendingDeletion(
                source_platform=platform,
                target_platform=tgt_map.platform,
                target_message_id=tgt_map.message_id,
                target_channel_id=tgt_map.channel_id,
                created_at=now,
            ))
            queued += 1
        db.commit()

    return JsonResponse({'queued': queued})


@csrf_exempt
@require_http_methods(['GET'])
def api_internal_bridge_pending_deletions(request, platform):
    """
    GET /ql/internal/bridge/pending-deletions/<platform>/
    Called by bots every 3s to pick up messages to delete on their platform.
    Returns up to 10 undelivered deletions and marks them delivered.

    platform = 'discord', 'fluxer', or 'matrix'
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if platform not in ('discord', 'fluxer', 'matrix'):
        return JsonResponse({'error': 'Invalid platform'}, status=400)

    now = int(time.time())
    cutoff = now - 300  # ignore deletions older than 5 minutes

    with get_db_session() as db:
        rows = (
            db.query(WebBridgePendingDeletion)
            .filter(
                WebBridgePendingDeletion.target_platform == platform,
                WebBridgePendingDeletion.delivered_at == None,
                WebBridgePendingDeletion.created_at >= cutoff,
            )
            .order_by(WebBridgePendingDeletion.created_at)
            .limit(10)
            .all()
        )

        if not rows:
            return JsonResponse({'deletions': []})

        ids = [r.id for r in rows]
        deletions = [
            {
                'id': r.id,
                'target_message_id': r.target_message_id,
                'target_channel_id': r.target_channel_id,
            }
            for r in rows
        ]

        db.query(WebBridgePendingDeletion).filter(
            WebBridgePendingDeletion.id.in_(ids)
        ).update({'delivered_at': now}, synchronize_session=False)
        db.commit()

    return JsonResponse({'deletions': deletions})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_bridge_typing(request):
    """
    POST /ql/api/internal/bridge/typing/
    Called by a bot when a user starts typing in a bridged channel.
    Returns the target channel ID(s) so the calling bot can fire the typing indicator there.

    Body: {"platform": "discord"|"fluxer", "channel_id": "..."}
    Response: {"targets": [{"platform": "...", "channel_id": "..."}]}
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    platform = str(data.get('platform', '')).strip()
    channel_id = str(data.get('channel_id', '')).strip()
    if not platform or not channel_id:
        return JsonResponse({'error': 'platform and channel_id required'}, status=400)

    targets = []
    with get_db_session() as db:
        if platform == 'discord':
            bridge = db.query(WebBridgeConfig).filter_by(
                discord_channel_id=channel_id, enabled=1
            ).first()
            if bridge and bridge.relay_discord_to_fluxer and bridge.fluxer_channel_id:
                targets.append({'platform': 'fluxer', 'channel_id': bridge.fluxer_channel_id})
        elif platform == 'fluxer':
            bridge = db.query(WebBridgeConfig).filter_by(
                fluxer_channel_id=channel_id, enabled=1
            ).first()
            if bridge and bridge.relay_fluxer_to_discord and bridge.discord_channel_id:
                targets.append({'platform': 'discord', 'channel_id': bridge.discord_channel_id})

    return JsonResponse({'targets': targets})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_guild_roles(request):
    """
    POST {"guild_id": "...", "roles": [{"id": "...", "name": "...", "color": 0, "position": 0, "managed": false}]}
    Bot syncs guild roles so the dashboard can show role pickers.
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    guild_id = str(data.get('guild_id', '')).strip()
    if not guild_id:
        return JsonResponse({'error': 'guild_id required'}, status=400)

    roles = data.get('roles', [])
    if not isinstance(roles, list):
        return JsonResponse({'error': 'roles must be a list'}, status=400)

    now = int(time.time())
    upserted = 0
    with get_db_session() as db:
        for role in roles:
            role_id = str(role.get('id', '')).strip()
            role_name = str(role.get('name', '')).strip()[:200]
            if not role_id or not role_name:
                continue
            # Skip @everyone
            if role_name == '@everyone':
                continue
            existing = db.query(WebFluxerGuildRole).filter_by(
                guild_id=guild_id, role_id=role_id
            ).first()
            if existing:
                existing.role_name = role_name
                existing.role_color = int(role.get('color', 0) or 0)
                existing.position = int(role.get('position', 0) or 0)
                existing.is_managed = 1 if role.get('managed') else 0
                existing.synced_at = now
            else:
                db.add(WebFluxerGuildRole(
                    guild_id=guild_id,
                    role_id=role_id,
                    role_name=role_name,
                    role_color=int(role.get('color', 0) or 0),
                    position=int(role.get('position', 0) or 0),
                    is_managed=1 if role.get('managed') else 0,
                    synced_at=now,
                ))
            upserted += 1
        db.commit()

    return JsonResponse({'success': True, 'upserted': upserted})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_guild_sync(request):
    """
    POST /ql/internal/guild-sync/
    Called by the Fluxer bot on on_ready (all guilds) and on_guild_join (single guild).
    Upserts the guild row with fresh metadata and cached resources.

    Body: {
        "guild_id": "123",
        "guild_name": "My Server",
        "owner_id": "456",          // optional
        "guild_icon_hash": "abc",   // optional
        "member_count": 100,        // optional
        "online_count": 50,         // optional
        "joined_at": 1700000000,    // only sent on first join (not during startup refresh)
        "channels": [{"id":"...", "name":"...", "type":0, "category_name":"..."}],
        "emojis": [{"id":"...", "name":"...", "animated":false}],
        "members": [{"id":"...", "username":"...", "display_name":"...", "avatar":"...", "roles":[...]}]
    }
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    guild_id = str(data.get('guild_id', '')).strip()
    if not guild_id:
        return JsonResponse({'error': 'guild_id required'}, status=400)

    guild_name = str(data.get('guild_name', '') or '').strip()[:100] or None
    owner_id = str(data.get('owner_id', '') or '').strip()[:25] or None
    guild_icon_hash = str(data.get('guild_icon_hash', '') or '').strip()[:255] or None
    member_count = int(data.get('member_count', 0) or 0)
    online_count = int(data.get('online_count', 0) or 0)
    joined_at_new = data.get('joined_at')  # Only set when bot is actually joining fresh

    channels = data.get('channels')
    emojis = data.get('emojis')
    members = data.get('members')

    now = int(time.time())

    with get_db_session() as db:
        settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()

        if settings:
            # Reactivate if bot had left
            settings.bot_present = 1
            settings.left_at = None
            if guild_name:
                settings.guild_name = guild_name
            if owner_id:
                settings.owner_id = owner_id
            if guild_icon_hash is not None:
                settings.guild_icon_hash = guild_icon_hash
            if member_count:
                settings.member_count = member_count
            if online_count is not None:
                settings.online_count = online_count
            if channels is not None:
                settings.cached_channels = json.dumps(channels)
            if emojis is not None:
                settings.cached_emojis = json.dumps(emojis)
            if members is not None:
                settings.cached_members = json.dumps(members)
            settings.updated_at = now
            created = False
        else:
            settings = WebFluxerGuildSettings(
                guild_id=guild_id,
                guild_name=guild_name,
                owner_id=owner_id,
                guild_icon_hash=guild_icon_hash,
                member_count=member_count,
                online_count=online_count,
                cached_channels=json.dumps(channels) if channels is not None else None,
                cached_emojis=json.dumps(emojis) if emojis is not None else None,
                cached_members=json.dumps(members) if members is not None else None,
                bot_present=1,
                joined_at=int(joined_at_new) if joined_at_new else now,
                created_at=now,
                updated_at=now,
            )
            db.add(settings)
            created = True

        # joined_at: only update when bot is re-joining (was previously left)
        if joined_at_new and not created and settings.left_at:
            settings.joined_at = int(joined_at_new)

        db.commit()

    logger.info(f"api_internal_guild_sync: {'created' if created else 'updated'} guild {guild_id} ({guild_name})")
    return JsonResponse({'success': True, 'created': created})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_guild_remove(request):
    """
    POST /ql/internal/guild-remove/
    Called by the Fluxer bot on on_guild_remove.
    Marks the guild as inactive (bot_present=False, left_at=now).
    All settings and cached data are preserved for potential rejoin.

    Body: {"guild_id": "123"}
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    guild_id = str(data.get('guild_id', '')).strip()
    if not guild_id:
        return JsonResponse({'error': 'guild_id required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        if settings:
            settings.bot_present = 0
            settings.left_at = now
            settings.updated_at = now
            db.commit()
            logger.info(f"api_internal_guild_remove: guild {guild_id} marked inactive")
            return JsonResponse({'success': True})

    return JsonResponse({'success': True, 'note': 'guild not found in DB'})


# =============================================================================
# GUILD ACTIONS (dashboard-initiated bot tasks: role creation, etc.)
# =============================================================================

@csrf_exempt
@require_http_methods(['GET'])
def api_internal_guild_actions_pending(request):
    """
    GET /ql/internal/guild-actions/?guild_id=X
    Called by the bot every 15s to pick up pending actions to execute.
    Returns up to 10 pending actions for this guild and marks them as 'processing'.
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    guild_id = request.GET.get('guild_id', '').strip()
    if not guild_id:
        return JsonResponse({'error': 'guild_id required'}, status=400)

    now = int(time.time())
    cutoff = now - 300  # ignore stale actions older than 5 min

    with get_db_session() as db:
        rows = (
            db.query(WebFluxerGuildAction)
            .filter(
                WebFluxerGuildAction.guild_id == guild_id,
                WebFluxerGuildAction.status == 'pending',
                WebFluxerGuildAction.created_at >= cutoff,
            )
            .order_by(WebFluxerGuildAction.created_at)
            .limit(10)
            .all()
        )

        if not rows:
            return JsonResponse({'actions': []})

        ids = [r.id for r in rows]
        actions = [
            {
                'id': r.id,
                'action_type': r.action_type,
                'payload': json.loads(r.payload_json),
            }
            for r in rows
        ]

        # Mark as processing to prevent duplicate execution
        db.query(WebFluxerGuildAction).filter(
            WebFluxerGuildAction.id.in_(ids)
        ).update({'status': 'processing'}, synchronize_session=False)
        db.commit()

    return JsonResponse({'actions': actions})


@csrf_exempt
@require_http_methods(['POST'])
def api_internal_guild_action_done(request, action_id):
    """
    POST /ql/internal/guild-actions/<id>/done/
    Called by the bot after executing an action to report the result.

    Body: {"success": true, "result": {...}}  OR  {"success": false, "error": "..."}
    """
    if not _check_bot_auth(request):
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        action = db.query(WebFluxerGuildAction).filter_by(id=action_id).first()
        if not action:
            return JsonResponse({'error': 'Action not found'}, status=404)

        if data.get('success'):
            action.status = 'done'
            action.result_json = json.dumps(data.get('result') or {})
        else:
            action.status = 'failed'
            action.result_json = json.dumps({'error': str(data.get('error', 'Unknown error'))})
        action.processed_at = now
        db.commit()


@require_http_methods(['GET'])
def api_bridge_media_proxy(request):
    """
    GET /ql/internal/bridge/media-proxy/?server=casual-heroes.com&id=abc123&filename=image.png
    Public proxy for Matrix media - downloads from Synapse with bot auth and streams to client.
    Used so Fluxer (which can't authenticate against Matrix) can display inline images.
    Rate-limited by nginx. Only serves matrix.casual-heroes.com media.
    """
    server = (request.GET.get('server') or '').strip()
    media_id = (request.GET.get('id') or '').strip()
    filename = (request.GET.get('filename') or 'file').strip()[:100]

    # Only proxy our own homeserver's media
    if not server or not media_id or server != 'casual-heroes.com':
        return HttpResponse(status=400)

    # Validate media_id is safe (alphanumeric + hyphens/underscores only)
    import re
    if not re.match(r'^[A-Za-z0-9_\-]+$', media_id):
        return HttpResponse(status=400)

    token = getattr(settings, 'MATRIX_ACCESS_TOKEN', '')
    if not token:
        return HttpResponse(status=503)

    url = f"https://matrix.casual-heroes.com/_matrix/client/v1/media/download/{server}/{media_id}"
    try:
        req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get('Content-Type', 'application/octet-stream')
            body = resp.read()
    except urllib.error.HTTPError as e:
        return HttpResponse(status=e.code)
    except Exception:
        return HttpResponse(status=502)

    response = HttpResponse(body, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    response['Cache-Control'] = 'public, max-age=86400'
    return response

    return JsonResponse({'ok': True})
