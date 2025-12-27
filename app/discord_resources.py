# app/discord_resources.py - Discord Resource Fetching
"""
Helper functions to fetch Discord resources (channels, roles, emojis) from the bot.
Uses caching to reduce API calls and prevent rate limiting.
"""

import os
import requests
from typing import Dict, List, Any, Optional
from .discord_cache import get_cache
import logging

logger = logging.getLogger(__name__)

# Bot's internal API endpoint (if it has one)
# Otherwise, we'll need to query the database for cached resources
BOT_API_URL = os.getenv('WARDEN_BOT_API_URL', 'http://localhost:8001')
BOT_API_TOKEN = os.getenv('WARDEN_BOT_API_TOKEN', '')


def get_guild_channels(guild_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Get channels for a guild with caching.

    Args:
        guild_id: Discord guild ID
        force_refresh: Force refresh from Discord API (skip cache)

    Returns:
        List of channel dictionaries with id, name, type, category_name
    """
    cache_key = f"guild_channels:{guild_id}"
    cache = get_cache()

    # Check cache first
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached channels for guild {guild_id}")
            return cached

    # Fetch from database (guild resources synced by bot)
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel
        import json

        with get_db_session() as db:
            guild = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            if guild and guild.cached_channels:
                channels = json.loads(guild.cached_channels)
                # Cache for 5 minutes
                cache.set(cache_key, channels, ttl=10)  # 10 second cache for near-realtime
                logger.debug(f"Loaded {len(channels)} channels from database for guild {guild_id}")
                return channels
    except Exception as e:
        logger.error(f"Failed to fetch channels for guild {guild_id}: {e}")

    logger.debug(f"No cached channels found for guild {guild_id}, returning empty list")
    return []


def get_guild_roles(guild_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Get roles for a guild with caching.

    Args:
        guild_id: Discord guild ID
        force_refresh: Force refresh from Discord API (skip cache)

    Returns:
        List of role dictionaries with id, name, color, position
    """
    cache_key = f"guild_roles:{guild_id}"
    cache = get_cache()

    # Check cache first
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached roles for guild {guild_id}")
            return cached

    # Fetch from database (guild resources synced by bot)
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel
        import json

        with get_db_session() as db:
            guild = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            if guild and guild.cached_roles:
                roles = json.loads(guild.cached_roles)
                # Cache for 5 minutes
                cache.set(cache_key, roles, ttl=10)  # 10 second cache for near-realtime
                logger.debug(f"Loaded {len(roles)} roles from database for guild {guild_id}")
                return roles
    except Exception as e:
        logger.error(f"Failed to fetch roles for guild {guild_id}: {e}")

    logger.debug(f"No cached roles found for guild {guild_id}, returning empty list")
    return []


def get_guild_emojis(guild_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Get custom emojis for a guild with caching.

    Args:
        guild_id: Discord guild ID
        force_refresh: Force refresh from Discord API (skip cache)

    Returns:
        List of emoji dictionaries with id, name, animated
    """
    cache_key = f"guild_emojis:{guild_id}"
    cache = get_cache()

    # Check cache first
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached emojis for guild {guild_id}")
            return cached

    # Fetch from database (guild resources synced by bot)
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel
        import json

        with get_db_session() as db:
            guild = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            if guild and guild.cached_emojis:
                emojis = json.loads(guild.cached_emojis)
                # Cache for 5 minutes
                cache.set(cache_key, emojis, ttl=10)  # 10 second cache for near-realtime
                logger.debug(f"Loaded {len(emojis)} emojis from database for guild {guild_id}")
                return emojis
    except Exception as e:
        logger.error(f"Failed to fetch emojis for guild {guild_id}: {e}")

    logger.debug(f"No cached emojis found for guild {guild_id}, returning empty list")
    return []


def get_guild_members(guild_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Get members for a guild with caching (industry standard: 5min TTL).

    Args:
        guild_id: Discord guild ID
        force_refresh: Force refresh from Discord API (skip cache)

    Returns:
        List of member dictionaries with id, username, discriminator, display_name, avatar, roles, joined_at
    """
    cache_key = f"guild_members:{guild_id}"
    cache = get_cache()

    # Check cache first
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached members for guild {guild_id}")
            return cached

    # Fetch from database (guild members synced by bot via Gateway events)
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel
        import json

        with get_db_session() as db:
            guild = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            if guild and guild.cached_members:
                members = json.loads(guild.cached_members)
                # Cache for 5 minutes (industry standard for member lists)
                cache.set(cache_key, members, ttl=300)
                logger.debug(f"Loaded {len(members)} members from database for guild {guild_id}")
                return members
    except Exception as e:
        logger.error(f"Failed to fetch members for guild {guild_id}: {e}")

    logger.debug(f"No cached members found for guild {guild_id}, returning empty list")
    return []


def get_guild_member(guild_id: str, user_id: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Get a single member from a guild with caching (1min TTL for permission checks).

    Args:
        guild_id: Discord guild ID
        user_id: Discord user ID
        force_refresh: Force refresh from Discord API (skip cache)

    Returns:
        Member dictionary or None if not found
    """
    cache_key = f"guild_member:{guild_id}:{user_id}"
    cache = get_cache()

    # Check cache first
    if not force_refresh:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Using cached member {user_id} for guild {guild_id}")
            return cached

    # Get from member list (which has its own cache)
    members = get_guild_members(guild_id)
    member = next((m for m in members if m['id'] == str(user_id)), None)

    if member:
        # Cache individual member for 1 minute (shorter TTL for permission checks)
        cache.set(cache_key, member, ttl=60)
        logger.debug(f"Cached member {user_id} from member list for guild {guild_id}")

    return member


def invalidate_guild_cache(guild_id: str):
    """
    Invalidate all cached resources for a guild.

    Args:
        guild_id: Discord guild ID
    """
    cache = get_cache()
    cache.delete(f"guild_channels:{guild_id}")
    cache.delete(f"guild_roles:{guild_id}")
    cache.delete(f"guild_emojis:{guild_id}")
    cache.delete(f"guild_members:{guild_id}")
    # Note: individual member caches (guild_member:*) will expire naturally in 1 minute
    logger.info(f"Invalidated cache for guild {guild_id}")
