"""
Custom context processors for adding data to all templates
"""
import json
import time

_emoji_cache = None
_emoji_cache_at = 0
_EMOJI_TTL = 300  # 5 minutes

def _get_emoji_map_json():
    global _emoji_cache, _emoji_cache_at
    now = time.time()
    if _emoji_cache is not None and now - _emoji_cache_at < _EMOJI_TTL:
        return _emoji_cache
    try:
        from .db import get_db_session
        from .questlog_web.models import WebCustomEmoji
        with get_db_session() as db:
            rows = db.query(WebCustomEmoji).all()
            m = {e.shortcode: e.image_url for e in rows}
        _emoji_cache = json.dumps(m)
        _emoji_cache_at = now
    except Exception:
        _emoji_cache = '{}'
    return _emoji_cache


def subscription_info(request):
    """Add subscription tier information to all template contexts."""
    # Extract guild_id from the current path if it exists
    path_parts = request.path.split('/')
    guild_id = None

    # Check if path contains a guild ID (format: /questlog/guild/<guild_id>/...)
    if 'guild' in path_parts:
        try:
            guild_idx = path_parts.index('guild')
            if guild_idx + 1 < len(path_parts):
                guild_id = path_parts[guild_idx + 1]
        except (ValueError, IndexError):
            pass

    # Default values
    context = {
        'is_vip': False,
        'subscription_tier': 'free',
        'user_network_status': None,
        'custom_emoji_map_json': _get_emoji_map_json(),
    }

    # If we have a guild_id, fetch the subscription info and network status
    if guild_id:
        try:
            from .db import get_db_session
            from .models import Guild as GuildModel, DiscoveryNetworkApplication

            with get_db_session() as db:
                guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
                if guild_record:
                    context['is_vip'] = guild_record.is_vip
                    context['subscription_tier'] = guild_record.subscription_tier if guild_record.subscription_tier else 'free'

                # Check Discovery Network status for this guild
                application = db.query(DiscoveryNetworkApplication).filter_by(
                    guild_id=int(guild_id)
                ).order_by(DiscoveryNetworkApplication.applied_at.desc()).first()

                if application:
                    context['user_network_status'] = application.status
        except Exception:
            # If there's any error, just use defaults
            pass

    return context
