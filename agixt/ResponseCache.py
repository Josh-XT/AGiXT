"""
Response Caching Middleware for AGiXT

This module provides a per-user response caching layer that dramatically improves
endpoint response times by caching GET responses and invalidating them when
mutations occur.

CACHING PHILOSOPHY - ALLOWLIST APPROACH:
=========================================
We use an explicit ALLOWLIST of endpoints that ARE cached, rather than caching
everything and excluding some. This is intentional because:

1. **Internal AGiXT data** (agents, prompts, chains, providers) - CACHEABLE
   - We control when this data changes (mutations go through our API)
   - We can invalidate cache on mutations

2. **External/Extension data** (PSA tickets, RMM assets, etc.) - NOT CACHEABLE
   - Data can change at any time by external systems/users
   - No invalidation signal when external data changes
   - Stale data could cause business problems (wrong ticket status, etc.)
   - Short TTL caching costs more resources than it saves (cache overhead)

3. **User/Billing data** - EXPLICITLY EXCLUDED
   - Token balance changes on every AI call
   - Financial data must always be fresh

Key features:
- Redis-backed cache shared across ALL workers (with local memory fallback)
- Per-user cache isolation (each user has their own cache entries)
- Automatic cache invalidation on mutations (POST, PUT, DELETE)
- Pattern-based invalidation (e.g., creating an agent invalidates agent list)
- TTL-based expiration
- Compression for efficient storage
- Allowlist approach: only explicitly listed endpoints are cached
"""

import time
import hashlib
import logging
import zlib
from typing import Dict, Optional, Any, Set, Callable
from dataclasses import dataclass
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A cached response retrieved from the cache"""

    response_body: bytes
    content_type: str
    status_code: int


class ResponseCacheManager:
    """
    Redis-backed response cache manager shared across all workers.

    Uses SharedCache for Redis-backed storage with automatic local memory fallback.
    This is MUCH faster than database-backed caching for HTTP response storage.

    Usage:
        cache_manager = ResponseCacheManager()

        # Get cached response
        cached = cache_manager.get(user_id, "/v1/agent")

        # Cache a response
        cache_manager.set(user_id, "/v1/agent", response_bytes, "application/json", 200)

        # Invalidate on mutation
        cache_manager.invalidate(user_id, "agent")  # Invalidates all agent-related caches

    IMPORTANT: This cache only stores GET responses. POST/PUT/DELETE responses are never cached.
    The cache key includes the full path + query string, so different query params = different cache entries.
    Request body is NOT considered since we only cache GET requests (which shouldn't have bodies).
    """

    # Cache key prefix for response cache entries
    CACHE_PREFIX = "response_cache"

    # Endpoints that should NEVER be cached (even if they match CACHEABLE_ENDPOINTS patterns)
    # These are excluded because their data changes frequently or is security-sensitive
    EXCLUDED_ENDPOINTS = {
        "/v1/user",  # Contains token_balance which changes on every AI completion
        "/v1/billing",  # All billing endpoints - balance changes frequently
        "/v1/login",  # Auth flow - should never cache
        "/v1/register",  # Auth flow - should never cache
        "/v1/logout",  # Auth flow
        "/v1/user/exists",  # Should always check real-time
        "/v1/user/verify",  # MFA/verification - security sensitive
        "/v1/user/mfa",  # MFA - security sensitive
        "/v1/oauth",  # OAuth flows - security sensitive
        "/v1/cache",  # Cache management endpoints themselves
        "/health",  # Health checks should be real-time
    }

    # Default TTLs per endpoint pattern (in seconds)
    DEFAULT_TTLS = {
        "/v1/agent": 120,  # Agent list - 2 minutes
        "/api/provider": 300,  # Providers - 5 minutes (rarely changes)
        "/v1/provider": 300,  # Provider list v1 - 5 minutes (rarely changes)
        "/v1/conversation": 30,  # Conversations - 30 seconds (changes often)
        "/v1/prompt": 300,  # Prompts - 5 minutes
        "/v1/chain": 300,  # Chains - 5 minutes
        "/v1/extension": 300,  # Extensions - 5 minutes
        "/v1/company": 60,  # Company data - 1 minute
        "/v1/scopes": 600,  # Scopes list - 10 minutes (rarely changes, system-level)
        "/v1/roles": 300,  # Custom roles - 5 minutes
        "/v1/user/scopes": 60,  # User's effective scopes - 1 minute (per-user, changes with role changes)
    }

    # Invalidation rules: when a mutation happens on path pattern, invalidate these cache patterns
    INVALIDATION_RULES = {
        # Agent mutations invalidate agent-related caches
        "POST:/v1/agent": ["agent", "company"],
        "PUT:/v1/agent": ["agent"],
        "DELETE:/v1/agent": ["agent", "company"],
        "PUT:/v1/agent/*/settings": ["agent"],
        "PUT:/v1/agent/*/commands": ["agent"],
        "PATCH:/v1/agent/*/command": ["agent", "extension"],  # Single command toggle
        "PATCH:/v1/agent/*/extension/commands": [
            "agent",
            "extension",
        ],  # Bulk command toggle
        # Conversation mutations
        "POST:/v1/conversation": ["conversation"],
        "DELETE:/v1/conversation": ["conversation"],
        # Company mutations
        "POST:/v1/company": ["company"],
        "PUT:/v1/company": ["company"],
        "PATCH:/v1/companies/*/command": [
            "agent",
            "extension",
            "company",
        ],  # Company command toggle
        "PATCH:/v1/companies/*/extension/commands": [
            "agent",
            "extension",
            "company",
        ],  # Company bulk toggle
        # Chain/Prompt mutations
        "POST:/v1/chain": ["chain"],
        "PUT:/v1/chain": ["chain"],
        "DELETE:/v1/chain": ["chain"],
        "POST:/v1/prompt": ["prompt"],
        "PUT:/v1/prompt": ["prompt"],
        "DELETE:/v1/prompt": ["prompt"],
        # Memory mutations
        "POST:/v1/agent/*/memory": ["memory"],
        "DELETE:/v1/agent/*/memory": ["memory"],
        # Extension mutations
        "PUT:/v1/agent/*/command": ["agent", "extension"],
        # Role/Scope mutations - invalidate role-related caches
        "POST:/v1/roles": [
            "roles",
            "user/scopes",
        ],  # Creating a role affects available roles
        "PUT:/v1/roles": [
            "roles",
            "user/scopes",
        ],  # Updating a role affects user scopes
        "DELETE:/v1/roles": [
            "roles",
            "user/scopes",
        ],  # Deleting a role affects user scopes
        "POST:/v1/user/*/roles": ["user/scopes"],  # Assigning role to user
        "DELETE:/v1/user/*/roles": ["user/scopes"],  # Removing role from user
        "PUT:/v1/company/*/user/*/role": [
            "user/scopes"
        ],  # Changing user's role in company
    }

    # Endpoints that should be cached (GET only) - ALLOWLIST APPROACH
    # ================================================================
    # ONLY endpoints listed here will be cached. Everything else passes through.
    # This is intentional - we only cache internal AGiXT data where we control
    # the mutation lifecycle and can properly invalidate.
    #
    # DO NOT add external data endpoints here (PSA tickets, RMM assets, etc.)
    # because we have no way to know when that external data changes.
    #
    # Note: Excluded endpoints take precedence over this list
    CACHEABLE_ENDPOINTS = {
        "/v1/agent",  # Agent list/config - internal AGiXT data
        "/api/provider",  # Provider list - internal, rarely changes
        "/v1/provider",  # Provider list v1 - internal, rarely changes
        "/v1/conversation",  # Conversation list - internal (short TTL)
        "/v1/prompt",  # Prompts - internal AGiXT data
        "/v1/chain",  # Chains - internal AGiXT data
        "/v1/extension",  # Extension metadata (NOT command execution)
        "/v1/company",  # Company data - internal AGiXT data
        "/api/extension/categories",  # Extension categories - internal
        "/v1/extensions/settings",  # Extension settings - internal config
        "/v1/scopes",  # All system scopes - internal, rarely changes
        "/v1/roles",  # Custom roles list - internal AGiXT data
        "/v1/user/scopes",  # User's effective scopes - per-user permissions
    }

    def __init__(self):
        from SharedCache import shared_cache

        self._cache = shared_cache
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
            "errors": 0,
        }

    def _make_cache_key(self, user_id: str, path: str, query_string: str = "") -> str:
        """Create a cache key from user_id, path and query string"""
        full_path = f"{path}?{query_string}" if query_string else path
        path_hash = hashlib.md5(full_path.encode()).hexdigest()
        return f"{self.CACHE_PREFIX}:{user_id}:{path_hash}"

    def _make_path_pattern_key(self, user_id: str, path: str) -> str:
        """Create a key for tracking paths per user (for invalidation)"""
        return f"{self.CACHE_PREFIX}:{user_id}:path:{path}"

    def _get_ttl(self, path: str) -> int:
        """Get TTL for a path based on patterns (in seconds)"""
        for pattern, ttl in self.DEFAULT_TTLS.items():
            if path.startswith(pattern):
                return ttl
        return 60  # Default 1 minute

    def _is_cacheable(self, path: str) -> bool:
        """Check if a path should be cached.

        Exclusions take precedence - if a path matches any excluded pattern,
        it will NOT be cached even if it matches a cacheable pattern.
        """
        # Check exclusions first - these take precedence
        for excluded_pattern in self.EXCLUDED_ENDPOINTS:
            if path.startswith(excluded_pattern):
                return False

        # Then check if it's in cacheable endpoints
        for pattern in self.CACHEABLE_ENDPOINTS:
            if path.startswith(pattern):
                return True
        return False

    def _match_invalidation_pattern(self, method: str, path: str) -> Set[str]:
        """Find which cache patterns should be invalidated for a mutation"""
        patterns_to_invalidate = set()

        for rule_pattern, invalidate_patterns in self.INVALIDATION_RULES.items():
            rule_method, rule_path = rule_pattern.split(":", 1)
            if method != rule_method:
                continue

            # Handle wildcard matching
            if "*" in rule_path:
                # Convert rule pattern to regex-like matching
                parts = rule_path.split("*")
                if len(parts) == 2:
                    prefix, suffix = parts
                    if path.startswith(prefix) and path.endswith(suffix):
                        patterns_to_invalidate.update(invalidate_patterns)
            elif path == rule_path or path.startswith(rule_path + "/"):
                patterns_to_invalidate.update(invalidate_patterns)

        return patterns_to_invalidate

    def get(
        self, user_id: str, path: str, query_string: str = ""
    ) -> Optional[CacheEntry]:
        """Get a cached response from Redis"""
        if not self._is_cacheable(path):
            return None

        try:
            import base64

            cache_key = self._make_cache_key(user_id, path, query_string)
            cached_data = self._cache.get(cache_key)

            if cached_data:
                self._stats["hits"] += 1
                logger.debug(f"Cache HIT: user={user_id[:8]}... path={path}")

                # Decompress the response body
                try:
                    compressed_body = base64.b64decode(cached_data["body"])
                    response_body = zlib.decompress(compressed_body)
                except (zlib.error, KeyError):
                    # Fallback for uncompressed or malformed data
                    response_body = (
                        cached_data.get("body", b"").encode()
                        if isinstance(cached_data.get("body"), str)
                        else cached_data.get("body", b"")
                    )

                return CacheEntry(
                    response_body=response_body,
                    content_type=cached_data.get("content_type", "application/json"),
                    status_code=cached_data.get("status_code", 200),
                )
            else:
                self._stats["misses"] += 1
                logger.debug(f"Cache MISS: user={user_id[:8]}... path={path}")
                return None

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"Cache GET error: {e}")
            return None

    def set(
        self,
        user_id: str,
        path: str,
        response_body: bytes,
        content_type: str,
        status_code: int,
        query_string: str = "",
    ):
        """Cache a response in Redis"""
        if not self._is_cacheable(path):
            return

        # Only cache successful responses
        if status_code != 200:
            return

        try:
            import base64

            cache_key = self._make_cache_key(user_id, path, query_string)
            ttl = self._get_ttl(path)

            # Compress the response body for efficient storage
            compressed_body = zlib.compress(response_body, level=6)

            # Store as a dict with metadata
            cache_data = {
                "body": base64.b64encode(compressed_body).decode("utf-8"),
                "content_type": content_type,
                "status_code": status_code,
                "path": path,
            }

            self._cache.set(cache_key, cache_data, ttl=ttl)

            # Also store a path reference for pattern-based invalidation
            path_key = self._make_path_pattern_key(user_id, path)
            existing_keys = self._cache.get(path_key) or []
            if cache_key not in existing_keys:
                existing_keys.append(cache_key)
                self._cache.set(path_key, existing_keys, ttl=ttl + 60)

            logger.debug(f"Cache SET: user={user_id[:8]}... path={path} ttl={ttl}s")

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"Cache SET error: {e}")

    def invalidate(self, user_id: str, method: str, path: str):
        """Invalidate caches based on a mutation"""
        patterns = self._match_invalidation_pattern(method, path)

        if not patterns:
            return

        try:
            deleted_count = 0

            # For any mutation that affects agent data, invalidate ALL cache for this user
            # This is aggressive but ensures data consistency
            # The granular pattern-based invalidation was unreliable due to MD5 hash keys
            if patterns:
                pattern = f"{self.CACHE_PREFIX}:{user_id}:*"
                deleted_count = self._cache.delete_pattern(pattern)

            self._stats["invalidations"] += deleted_count
            logger.debug(
                f"Cache INVALIDATE: user={user_id[:8]}... patterns={patterns} deleted={deleted_count}"
            )

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"Cache INVALIDATE error: {e}")

    def invalidate_user(self, user_id: str):
        """Clear all caches for a user"""
        try:
            # Delete all keys for this user
            pattern = f"{self.CACHE_PREFIX}:{user_id}:*"
            deleted = self._cache.delete_pattern(pattern)
            logger.debug(f"Cache CLEAR: user={user_id[:8]}... deleted={deleted}")

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"Cache CLEAR error: {e}")

    def clear_all(self):
        """Clear all response caches for all users"""
        try:
            # Delete all response cache keys
            pattern = f"{self.CACHE_PREFIX}:*"
            deleted = self._cache.delete_pattern(pattern)
            self._stats = {
                "hits": 0,
                "misses": 0,
                "invalidations": 0,
                "errors": 0,
            }
            logger.info(f"Cache CLEAR ALL: deleted={deleted} entries")

        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"Cache CLEAR ALL error: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            hit_rate = (
                self._stats["hits"]
                / (self._stats["hits"] + self._stats["misses"])
                * 100
                if (self._stats["hits"] + self._stats["misses"]) > 0
                else 0
            )

            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate_percent": round(hit_rate, 2),
                "invalidations": self._stats["invalidations"],
                "errors": self._stats["errors"],
                "storage": "redis" if self._cache._redis else "local_memory",
            }

        except Exception as e:
            # Log detailed error server-side, but do not expose exception details to clients
            logger.warning(f"Cache stats error: {e}")
            return {
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate_percent": 0,
                "invalidations": self._stats["invalidations"],
                "errors": self._stats["errors"],
                "storage": "unknown",
                "error": "internal error while retrieving cache statistics",
            }


# Global cache manager instance
_cache_manager: Optional[ResponseCacheManager] = None


def get_cache_manager() -> ResponseCacheManager:
    """Get the global cache manager instance"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = ResponseCacheManager()
    return _cache_manager


def extract_user_id(request: Request) -> Optional[str]:
    """Extract user ID from request authorization"""
    auth_header = request.headers.get("authorization", "")
    if not auth_header:
        return None

    token = auth_header.replace("Bearer ", "").replace("bearer ", "")
    if not token:
        return None

    # Use token hash as user identifier (avoids JWT decode overhead)
    return hashlib.md5(token.encode()).hexdigest()


class ResponseCacheMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that caches GET responses and invalidates on mutations.

    Uses Redis (via SharedCache) for shared storage across ALL workers.
    Falls back to local memory if Redis is unavailable.

    Add to app:
        from ResponseCache import ResponseCacheMiddleware
        app.add_middleware(ResponseCacheMiddleware)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip non-API paths
        path = request.url.path
        if not path.startswith("/v1/") and not path.startswith("/api/"):
            return await call_next(request)

        # Extract user ID
        user_id = extract_user_id(request)
        if not user_id:
            return await call_next(request)

        cache_manager = get_cache_manager()
        method = request.method.upper()
        query_string = str(request.url.query)

        # For GET requests, try to return cached response
        if method == "GET":
            cached = cache_manager.get(user_id, path, query_string)
            if cached:
                return Response(
                    content=cached.response_body,
                    status_code=cached.status_code,
                    media_type=cached.content_type,
                    headers={"X-Cache": "HIT"},
                )

        # Call the actual endpoint
        response = await call_next(request)

        # For mutations, invalidate relevant caches
        if method in ("POST", "PUT", "DELETE", "PATCH"):
            cache_manager.invalidate(user_id, method, path)

        # For successful GET requests, try to cache the response
        if method == "GET" and response.status_code == 200:
            # Check if this endpoint is cacheable BEFORE reading body
            if not cache_manager._is_cacheable(path):
                # Not cacheable - return response without X-Cache header
                return response

            # We need to read the response body to cache it
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            cache_manager.set(
                user_id=user_id,
                path=path,
                response_body=response_body,
                content_type=response.media_type or "application/json",
                status_code=response.status_code,
                query_string=query_string,
            )

            # Return new response with cached body and X-Cache header
            return Response(
                content=response_body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers={**dict(response.headers), "X-Cache": "MISS"},
            )

        return response


# Utility function to manually invalidate cache (for use in endpoints)
def invalidate_user_cache(user_id: str, patterns: Optional[Set[str]] = None):
    """
    Manually invalidate cache for a user.

    Usage in endpoints:
        from ResponseCache import invalidate_user_cache
        invalidate_user_cache(auth.user_id, {"agent", "user"})
    """
    cache_manager = get_cache_manager()
    if patterns:
        # Invalidate specific patterns by constructing fake mutations
        for pattern in patterns:
            cache_manager.invalidate(user_id, "DELETE", f"/v1/{pattern}")
    else:
        cache_manager.invalidate_user(user_id)
