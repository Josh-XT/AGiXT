"""
Response Caching Middleware for AGiXT

This module provides a per-user response caching layer that dramatically improves
endpoint response times by caching GET responses and invalidating them when
mutations occur.

Key features:
- Per-user cache isolation (each user has their own cache)
- Automatic cache invalidation on mutations (POST, PUT, DELETE)
- Pattern-based invalidation (e.g., creating an agent invalidates agent list)
- TTL-based expiration as a fallback
- Memory-efficient with LRU eviction
"""

import time
import hashlib
import logging
import json
from typing import Dict, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from collections import OrderedDict
from functools import wraps
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cached response"""
    response_body: bytes
    content_type: str
    status_code: int
    created_at: float
    ttl: float  # seconds
    
    def is_expired(self) -> bool:
        return time.time() > (self.created_at + self.ttl)


@dataclass
class UserCache:
    """Per-user cache with LRU eviction"""
    entries: OrderedDict = field(default_factory=OrderedDict)
    max_entries: int = 100
    
    def get(self, key: str) -> Optional[CacheEntry]:
        if key in self.entries:
            # Move to end (most recently used)
            self.entries.move_to_end(key)
            entry = self.entries[key]
            if not entry.is_expired():
                return entry
            else:
                # Remove expired entry
                del self.entries[key]
        return None
    
    def set(self, key: str, entry: CacheEntry):
        # Evict oldest entries if at capacity
        while len(self.entries) >= self.max_entries:
            self.entries.popitem(last=False)
        self.entries[key] = entry
    
    def invalidate(self, pattern: str):
        """Invalidate all entries matching a pattern"""
        keys_to_remove = [
            key for key in self.entries.keys()
            if pattern in key or key.startswith(pattern)
        ]
        for key in keys_to_remove:
            del self.entries[key]
    
    def clear(self):
        """Clear all entries"""
        self.entries.clear()


class ResponseCacheManager:
    """
    Manages response caching across all users.
    
    Usage:
        cache_manager = ResponseCacheManager()
        
        # Get cached response
        cached = cache_manager.get(user_id, "/v1/agent")
        
        # Cache a response
        cache_manager.set(user_id, "/v1/agent", response_bytes, "application/json", 200)
        
        # Invalidate on mutation
        cache_manager.invalidate(user_id, "agent")  # Invalidates all agent-related caches
    """
    
    # Default TTLs per endpoint pattern (in seconds)
    DEFAULT_TTLS = {
        "/v1/user": 60,           # User data - 1 minute
        "/v1/agent": 120,         # Agent list - 2 minutes
        "/api/provider": 300,     # Providers - 5 minutes (rarely changes)
        "/v1/conversation": 30,   # Conversations - 30 seconds (changes often)
        "/v1/prompt": 300,        # Prompts - 5 minutes
        "/v1/chain": 300,         # Chains - 5 minutes
        "/v1/extension": 300,     # Extensions - 5 minutes
    }
    
    # Invalidation rules: when a mutation happens on path pattern, invalidate these cache patterns
    INVALIDATION_RULES = {
        # Agent mutations invalidate agent-related caches
        "POST:/v1/agent": ["agent", "user"],
        "PUT:/v1/agent": ["agent"],
        "DELETE:/v1/agent": ["agent", "user"],
        "PUT:/v1/agent/*/settings": ["agent"],
        "PUT:/v1/agent/*/commands": ["agent"],
        
        # Conversation mutations
        "POST:/v1/conversation": ["conversation"],
        "DELETE:/v1/conversation": ["conversation"],
        
        # User mutations invalidate user cache
        "PUT:/v1/user": ["user"],
        
        # Company mutations
        "POST:/v1/company": ["user", "company"],
        "PUT:/v1/company": ["user", "company"],
        
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
    }
    
    # Endpoints that should be cached (GET only)
    CACHEABLE_ENDPOINTS = {
        "/v1/user",
        "/v1/agent",
        "/api/provider",
        "/v1/conversation",
        "/v1/prompt",
        "/v1/chain",
        "/v1/extension",
    }
    
    def __init__(self, max_users: int = 10000, max_entries_per_user: int = 100):
        self._caches: Dict[str, UserCache] = {}
        self._max_users = max_users
        self._max_entries_per_user = max_entries_per_user
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }
        self._lock = asyncio.Lock()
    
    def _get_user_cache(self, user_id: str) -> UserCache:
        """Get or create a user's cache"""
        if user_id not in self._caches:
            # Evict oldest user cache if at capacity
            if len(self._caches) >= self._max_users:
                oldest_user = next(iter(self._caches))
                del self._caches[oldest_user]
            self._caches[user_id] = UserCache(max_entries=self._max_entries_per_user)
        return self._caches[user_id]
    
    def _make_cache_key(self, path: str, query_string: str = "") -> str:
        """Create a cache key from path and query string"""
        full_path = f"{path}?{query_string}" if query_string else path
        return hashlib.md5(full_path.encode()).hexdigest()
    
    def _get_ttl(self, path: str) -> float:
        """Get TTL for a path based on patterns"""
        for pattern, ttl in self.DEFAULT_TTLS.items():
            if path.startswith(pattern):
                return ttl
        return 60  # Default 1 minute
    
    def _is_cacheable(self, path: str) -> bool:
        """Check if a path should be cached"""
        for pattern in self.CACHEABLE_ENDPOINTS:
            if path.startswith(pattern):
                return True
        return False
    
    def _match_invalidation_pattern(self, method: str, path: str) -> Set[str]:
        """Find which cache patterns should be invalidated for a mutation"""
        patterns_to_invalidate = set()
        method_path = f"{method}:{path}"
        
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
    
    def get(self, user_id: str, path: str, query_string: str = "") -> Optional[CacheEntry]:
        """Get a cached response"""
        if not self._is_cacheable(path):
            return None
        
        cache = self._get_user_cache(user_id)
        key = self._make_cache_key(path, query_string)
        entry = cache.get(key)
        
        if entry:
            self._stats["hits"] += 1
            logger.debug(f"Cache HIT: user={user_id[:8]}... path={path}")
        else:
            self._stats["misses"] += 1
            logger.debug(f"Cache MISS: user={user_id[:8]}... path={path}")
        
        return entry
    
    def set(
        self,
        user_id: str,
        path: str,
        response_body: bytes,
        content_type: str,
        status_code: int,
        query_string: str = "",
    ):
        """Cache a response"""
        if not self._is_cacheable(path):
            return
        
        # Only cache successful responses
        if status_code != 200:
            return
        
        cache = self._get_user_cache(user_id)
        key = self._make_cache_key(path, query_string)
        ttl = self._get_ttl(path)
        
        entry = CacheEntry(
            response_body=response_body,
            content_type=content_type,
            status_code=status_code,
            created_at=time.time(),
            ttl=ttl,
        )
        cache.set(key, entry)
        logger.debug(f"Cache SET: user={user_id[:8]}... path={path} ttl={ttl}s")
    
    def invalidate(self, user_id: str, method: str, path: str):
        """Invalidate caches based on a mutation"""
        patterns = self._match_invalidation_pattern(method, path)
        
        if not patterns:
            return
        
        cache = self._get_user_cache(user_id)
        for pattern in patterns:
            cache.invalidate(pattern)
            self._stats["invalidations"] += 1
            logger.debug(f"Cache INVALIDATE: user={user_id[:8]}... pattern={pattern}")
    
    def invalidate_user(self, user_id: str):
        """Clear all caches for a user"""
        if user_id in self._caches:
            self._caches[user_id].clear()
            logger.debug(f"Cache CLEAR: user={user_id[:8]}...")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_entries = sum(len(c.entries) for c in self._caches.values())
        hit_rate = (
            self._stats["hits"] / (self._stats["hits"] + self._stats["misses"]) * 100
            if (self._stats["hits"] + self._stats["misses"]) > 0
            else 0
        )
        return {
            "users": len(self._caches),
            "total_entries": total_entries,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "invalidations": self._stats["invalidations"],
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
        
        # For successful GET requests, cache the response
        if method == "GET" and response.status_code == 200:
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
            
            # Return new response with cached body
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
        cache = cache_manager._get_user_cache(user_id)
        for pattern in patterns:
            cache.invalidate(pattern)
    else:
        cache_manager.invalidate_user(user_id)
