"""
Custom context processors for adding data to all templates
"""

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
    }

    # If we have a guild_id, fetch the subscription info
    if guild_id:
        try:
            from .db import get_db_session
            from .models import Guild as GuildModel

            with get_db_session() as db:
                guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
                if guild_record:
                    context['is_vip'] = guild_record.is_vip
                    context['subscription_tier'] = guild_record.subscription_tier if guild_record.subscription_tier else 'free'
        except Exception:
            # If there's any error, just use defaults
            pass

    return context
