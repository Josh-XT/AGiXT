"""
SharedCache - Cross-worker caching with Redis backend

This module provides a shared cache that works across multiple uvicorn workers.
It uses Redis as the backend when available, falling back to local memory if Redis
is not configured or unavailable.

The cache supports:
- TTL-based expiration
- Automatic JSON serialization/deserialization
- Graceful fallback to local memory
- Prefix-based key namespacing
- Cache invalidation (single key or pattern-based)

Usage:
    from SharedCache import shared_cache

    # Get with default
    value = shared_cache.get("my_key", default=None)

    # Set with TTL (seconds)
    shared_cache.set("my_key", {"data": "value"}, ttl=60)

    # Delete
    shared_cache.delete("my_key")

    # Delete by pattern (only works with Redis)
    shared_cache.delete_pattern("agent:*")
"""

import json
import time
import logging
import os
from typing import Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)


class SharedCache:
    """
    A shared cache that uses Redis when available, falling back to local memory.

    This solves the multi-worker cache invalidation problem by using Redis as
    a shared backend that all workers can read from and write to.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Singleton pattern to ensure one cache instance per process"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._redis = None
        self._local_cache = {}  # Fallback
        self._local_cache_lock = Lock()
        self._prefix = "agixt:"

        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection if configured"""
        redis_host = os.environ.get("REDIS_HOST", "")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        redis_password = os.environ.get("REDIS_PASSWORD", "")
        redis_db = int(os.environ.get("REDIS_DB", "0"))

        if not redis_host:
            logger.info(
                "SharedCache: No REDIS_HOST configured, using local memory cache"
            )
            return

        try:
            import redis

            self._redis = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password if redis_password else None,
                db=redis_db,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )

            # Test connection
            self._redis.ping()

        except ImportError:
            logger.warning(
                "SharedCache: redis package not installed, using local memory cache"
            )
            self._redis = None
        except Exception as e:
            logger.warning(
                f"SharedCache: Failed to connect to Redis ({e}), using local memory cache"
            )
            self._redis = None

    @property
    def is_redis_available(self) -> bool:
        """Check if Redis is currently available"""
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except:
            return False

    def _make_key(self, key: str) -> str:
        """Create a prefixed key"""
        return f"{self._prefix}{key}"

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the cache.

        Args:
            key: The cache key
            default: Default value if key not found

        Returns:
            The cached value or default
        """
        full_key = self._make_key(key)

        if self._redis is not None:
            try:
                value = self._redis.get(full_key)
                if value is None:
                    return default
                return json.loads(value)
            except Exception as e:
                logger.debug(f"SharedCache Redis get error: {e}")
                # Fall through to local cache

        # Local cache fallback
        with self._local_cache_lock:
            entry = self._local_cache.get(full_key)
            if entry is None:
                return default

            # Check TTL
            if entry["expires_at"] and time.time() > entry["expires_at"]:
                del self._local_cache[full_key]
                return default

            return entry["value"]

    def set(self, key: str, value: Any, ttl: int = 0) -> bool:
        """
        Set a value in the cache.

        Args:
            key: The cache key
            value: The value to cache (must be JSON serializable)
            ttl: Time-to-live in seconds (0 = no expiration)

        Returns:
            True if successful
        """
        full_key = self._make_key(key)

        try:
            serialized = json.dumps(value)
        except (TypeError, ValueError) as e:
            # logger.error(f"SharedCache: Failed to serialize value for key {key}: {e}")
            return False

        if self._redis is not None:
            try:
                if ttl > 0:
                    self._redis.setex(full_key, ttl, serialized)
                else:
                    self._redis.set(full_key, serialized)
                return True
            except Exception as e:
                logger.debug(f"SharedCache Redis set error: {e}")
                # Fall through to local cache

        # Local cache fallback
        with self._local_cache_lock:
            self._local_cache[full_key] = {
                "value": value,
                "expires_at": time.time() + ttl if ttl > 0 else None,
            }
        return True

    def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: The cache key

        Returns:
            True if the key was deleted
        """
        full_key = self._make_key(key)

        deleted = False

        if self._redis is not None:
            try:
                deleted = self._redis.delete(full_key) > 0
            except Exception as e:
                logger.debug(f"SharedCache Redis delete error: {e}")

        # Always clean local cache too
        with self._local_cache_lock:
            if full_key in self._local_cache:
                del self._local_cache[full_key]
                deleted = True

        return deleted

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Note: Pattern matching only works with Redis. Local cache will
        attempt prefix matching.

        Args:
            pattern: Key pattern (e.g., "agent:*" or "company:123:*")

        Returns:
            Number of keys deleted
        """
        full_pattern = self._make_key(pattern)
        count = 0

        if self._redis is not None:
            try:
                # Use SCAN to avoid blocking
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(
                        cursor, match=full_pattern, count=100
                    )
                    if keys:
                        count += self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.debug(f"SharedCache Redis delete_pattern error: {e}")

        # Local cache - simple prefix matching
        with self._local_cache_lock:
            # Convert glob pattern to prefix (basic support)
            prefix = full_pattern.replace("*", "")
            keys_to_delete = [
                k for k in self._local_cache.keys() if k.startswith(prefix)
            ]
            for key in keys_to_delete:
                del self._local_cache[key]
                count += 1

        return count

    def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: The cache key

        Returns:
            True if the key exists
        """
        full_key = self._make_key(key)

        if self._redis is not None:
            try:
                return self._redis.exists(full_key) > 0
            except Exception as e:
                logger.debug(f"SharedCache Redis exists error: {e}")

        with self._local_cache_lock:
            entry = self._local_cache.get(full_key)
            if entry is None:
                return False
            if entry["expires_at"] and time.time() > entry["expires_at"]:
                del self._local_cache[full_key]
                return False
            return True

    def clear_local(self):
        """Clear only the local fallback cache"""
        with self._local_cache_lock:
            self._local_cache.clear()

    def get_stats(self) -> dict:
        """Get cache statistics"""
        stats = {
            "backend": "redis" if self._redis is not None else "local",
            "redis_available": self.is_redis_available,
            "local_cache_size": len(self._local_cache),
        }

        if self._redis is not None and self.is_redis_available:
            try:
                info = self._redis.info("memory")
                stats["redis_used_memory"] = info.get("used_memory_human", "unknown")

                # Count our keys
                cursor = 0
                key_count = 0
                while True:
                    cursor, keys = self._redis.scan(
                        cursor, match=f"{self._prefix}*", count=100
                    )
                    key_count += len(keys)
                    if cursor == 0:
                        break
                stats["redis_key_count"] = key_count
            except:
                pass

        return stats


# Singleton instance
shared_cache = SharedCache()


# Convenience functions for common cache patterns


def cache_agent_data(agent_id: str, user_id: str, data: dict, ttl: int = 5):
    """Cache agent data with standard key format"""
    key = f"agent:{agent_id}:{user_id}"
    shared_cache.set(key, data, ttl=ttl)


def get_cached_agent_data(agent_id: str, user_id: str) -> Optional[dict]:
    """Get cached agent data"""
    key = f"agent:{agent_id}:{user_id}"
    return shared_cache.get(key)


def invalidate_agent_cache(agent_id: str = None, user_id: str = None):
    """Invalidate agent cache - by agent, by user, or all"""
    if agent_id and user_id:
        shared_cache.delete(f"agent:{agent_id}:{user_id}")
    elif agent_id:
        shared_cache.delete_pattern(f"agent:{agent_id}:*")
    elif user_id:
        shared_cache.delete_pattern(f"agent:*:{user_id}")
    else:
        shared_cache.delete_pattern("agent:*")


def cache_company_config(company_id: str, config: dict, ttl: int = 60):
    """Cache company agent config"""
    key = f"company_config:{company_id}"
    shared_cache.set(key, config, ttl=ttl)


def get_cached_company_config(company_id: str) -> Optional[dict]:
    """Get cached company config"""
    key = f"company_config:{company_id}"
    return shared_cache.get(key)


def invalidate_company_config_cache(company_id: str = None):
    """Invalidate company config cache"""
    if company_id:
        shared_cache.delete(f"company_config:{company_id}")
    else:
        shared_cache.delete_pattern("company_config:*")


def cache_commands(commands: list, ttl: int = 300):
    """Cache all commands list"""
    shared_cache.set("all_commands", commands, ttl=ttl)


def get_cached_commands() -> Optional[list]:
    """Get cached commands list"""
    return shared_cache.get("all_commands")


def invalidate_commands_cache():
    """Invalidate commands cache"""
    shared_cache.delete("all_commands")


def cache_sso_providers(providers: list, ttl: int = 600):
    """Cache SSO providers list"""
    shared_cache.set("sso_providers", providers, ttl=ttl)


def get_cached_sso_providers() -> Optional[list]:
    """Get cached SSO providers"""
    return shared_cache.get("sso_providers")


def invalidate_sso_providers_cache():
    """Invalidate SSO providers cache"""
    shared_cache.delete("sso_providers")
