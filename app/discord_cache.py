# app/discord_cache.py - Discord API Response Caching
"""
In-memory caching for Discord API responses to reduce rate limiting.
Caches guild channels, roles, and emojis with TTL.
"""

import time
from typing import Dict, Any, Optional
import threading

class DiscordCache:
    """Thread-safe in-memory cache for Discord API responses."""

    def __init__(self, default_ttl: int = 300):
        """
        Initialize cache.

        Args:
            default_ttl: Default time-to-live in seconds (5 minutes)
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]
            if time.time() > entry['expires_at']:
                # Expired - remove from cache
                del self._cache[key]
                return None

            return entry['value']

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
        """
        with self._lock:
            self._cache[key] = {
                'value': value,
                'expires_at': time.time() + (ttl or self.default_ttl)
            }

    def delete(self, key: str):
        """
        Delete value from cache.

        Args:
            key: Cache key
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self):
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_entries = len(self._cache)
            expired_entries = sum(
                1 for entry in self._cache.values()
                if time.time() > entry['expires_at']
            )

            return {
                'total_entries': total_entries,
                'active_entries': total_entries - expired_entries,
                'expired_entries': expired_entries
            }


# Global cache instance
_discord_cache = DiscordCache(default_ttl=10)  # 10 seconds for near-realtime updates


def get_cache() -> DiscordCache:
    """Get the global Discord cache instance."""
    return _discord_cache
