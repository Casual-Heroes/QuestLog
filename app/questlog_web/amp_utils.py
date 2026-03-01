# AMP (CubeCoders Application Management Panel) utilities for QuestLog Web
# Provides game server status integration

import os
import logging
import asyncio
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

# Import AMP API components
try:
    from ampapi.dataclass import APIParams
    from ampapi.bridge import Bridge
    from ampapi.controller import AMPControllerInstance
    AMP_AVAILABLE = True
except ImportError:
    logger.warning("ampapi not installed - AMP features will be disabled")
    AMP_AVAILABLE = False

# Cache for AMP data (reuse Django's cache)
try:
    from django.core.cache import cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    cache = None

# Cache TTL
AMP_CACHE_TTL = 60  # 60 seconds


def get_amp_credentials() -> tuple:
    """Get AMP credentials from environment."""
    return (
        os.getenv("AMP_URL"),
        os.getenv("AMP_USER"),
        os.getenv("AMP_PASSWORD")
    )


def get_cached_amp_data(instance_name: str) -> Optional[Dict]:
    """Get cached AMP instance data."""
    if not CACHE_AVAILABLE or not cache:
        return None

    cache_key = f"amp_instance:{instance_name}"
    data = cache.get(cache_key)
    if data:
        logger.debug(f"AMP cache HIT for {instance_name}")
    return data


def set_cached_amp_data(instance_name: str, data: Dict):
    """Cache AMP instance data."""
    if not CACHE_AVAILABLE or not cache:
        return

    cache_key = f"amp_instance:{instance_name}"
    cache.set(cache_key, data, timeout=AMP_CACHE_TTL)
    logger.debug(f"Cached AMP data for {instance_name} (TTL: {AMP_CACHE_TTL}s)")


async def fetch_amp_instance_data(instance_name: str) -> Optional[Dict]:
    """
    Fetch game server data from AMP instance.

    Args:
        instance_name: The AMP instance identifier

    Returns:
        Server data dict or None on failure
    """
    if not AMP_AVAILABLE:
        logger.warning("AMP API not available")
        return get_amp_fallback(instance_name)

    # Check cache first
    cached = get_cached_amp_data(instance_name)
    if cached:
        return cached

    url, user, password = get_amp_credentials()
    if not all([url, user, password]):
        logger.warning("AMP credentials not configured")
        return get_amp_fallback(instance_name)

    try:
        params = APIParams(url=url, user=user, password=password)
        bridge = Bridge(params)
        controller = AMPControllerInstance(bridge)

        instances = controller.get_instances()

        for instance in instances:
            if instance.InstanceName == instance_name or instance.FriendlyName == instance_name:
                # Get player count
                online = 0
                max_players = 0

                try:
                    status = instance.get_updates()
                    online = status.get('Players', {}).get('Current', 0)
                    max_players = status.get('Players', {}).get('Maximum', 0)
                except Exception as e:
                    logger.warning(f"Could not get player count for {instance_name}: {e}")

                # Build server data
                data = {
                    "id": instance_name,
                    "name": instance.FriendlyName or instance_name,
                    "title": instance.FriendlyName or instance_name,
                    "online": online,
                    "max": max_players,
                    "status": "online" if instance.Running else "offline",
                    "status_label": "Online" if instance.Running else "Offline",
                    "ip": instance.IP if hasattr(instance, 'IP') else None,
                    "port": instance.Port if hasattr(instance, 'Port') else None,
                    "live_now": online > 0,
                }

                # Cache the data
                set_cached_amp_data(instance_name, data)
                return data

        logger.warning(f"AMP instance {instance_name} not found")
        return get_amp_fallback(instance_name)

    except Exception as e:
        logger.error(f"Error fetching AMP data for {instance_name}: {e}")
        return get_amp_fallback(instance_name)


def get_amp_fallback(instance_name: str) -> Dict:
    """Return fallback data when AMP is unavailable."""
    return {
        "id": instance_name,
        "name": instance_name,
        "title": instance_name,
        "online": "-",
        "max": "-",
        "status": "unknown",
        "status_label": "Unknown",
        "ip": None,
        "port": None,
        "live_now": False,
    }


async def fetch_multiple_amp_instances(instance_names: List[str]) -> Dict[str, Dict]:
    """
    Fetch data for multiple AMP instances in parallel.

    Args:
        instance_names: List of instance names to fetch

    Returns:
        Dict mapping instance name to server data
    """
    if not instance_names:
        return {}

    tasks = [fetch_amp_instance_data(name) for name in instance_names]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    data_map = {}
    for name, result in zip(instance_names, results):
        if isinstance(result, Exception):
            logger.error(f"Error fetching {name}: {result}")
            data_map[name] = get_amp_fallback(name)
        elif result:
            data_map[name] = result
        else:
            data_map[name] = get_amp_fallback(name)

    return data_map


def get_amp_instances_sync(instance_names: List[str]) -> Dict[str, Dict]:
    """
    Synchronous wrapper for fetch_multiple_amp_instances.
    Use this in Django views.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(fetch_multiple_amp_instances(instance_names))
    finally:
        loop.close()
