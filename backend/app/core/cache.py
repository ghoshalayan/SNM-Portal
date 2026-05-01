"""In-process TTL cache with namespace-level invalidation.

Thread-safe, no external dependencies. Swappable with Redis later if
horizontal scaling is needed — caller API stays the same.

Usage (functional):
    from app.core.cache import cache_get, cache_set, invalidate

    key = f"visible:{user_id}:{company_id}"
    hit = cache_get("visibility", key)
    if hit is not None:
        return hit
    value = expensive_computation()
    cache_set("visibility", key, value, ttl=300)
    return value

Usage (decorator):
    @cached("role_perms", ttl=600)
    def get_role_perm(role_id, menu_name): ...

Invalidation:
    invalidate("visibility", key)              # single key
    invalidate_namespace("visibility")          # entire namespace
    invalidate_user("visibility", user_id)     # all keys containing "{user_id}:"

Design choices:
- TTLCache per namespace — isolates size caps (visibility cache won't evict menus)
- RLock per namespace — fine-grained locking, avoids global contention
- maxsize chosen to fit expected concurrent users (1024 covers 500 users x 2 companies)
- Safe to call from any thread; every access is lock-protected
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from threading import RLock
from typing import Any, Callable, Dict, Optional, Tuple

from cachetools import TTLCache


# --------------------------------------------------------------------- #
# Namespace registry                                                     #
# --------------------------------------------------------------------- #

@dataclass
class _Namespace:
    cache: TTLCache
    lock: RLock


_REGISTRY: Dict[str, _Namespace] = {}
_REGISTRY_LOCK = RLock()

# Default TTLs (seconds) per known namespace — tuned for expected change frequency
_DEFAULT_CONFIG: Dict[str, Tuple[int, int]] = {
    # namespace        (ttl,  maxsize)
    "visibility":      (300, 2048),    # visible_user_ids (invalidated on UserRoleMap/Role change)
    "location":        (300, 2048),    # LocationAccess (invalidated on UserLocationMap change)
    "role_perms":      (600, 4096),    # RoleMenuMap lookups
    "role_settings":   (600, 512),     # Role full object
    "menu_tree":       (900, 512),     # User menu tree
    "master":          (1800, 2048),   # master data by (entity, company_id)
    "company":         (1800, 256),    # Company objects
    "default":         (300, 1024),    # catch-all
}


def _get_or_create(namespace: str) -> _Namespace:
    """Lazily create a namespace with defaults from the registry."""
    ns = _REGISTRY.get(namespace)
    if ns is not None:
        return ns
    with _REGISTRY_LOCK:
        ns = _REGISTRY.get(namespace)
        if ns is None:
            ttl, maxsize = _DEFAULT_CONFIG.get(namespace, _DEFAULT_CONFIG["default"])
            ns = _Namespace(cache=TTLCache(maxsize=maxsize, ttl=ttl), lock=RLock())
            _REGISTRY[namespace] = ns
    return ns


# --------------------------------------------------------------------- #
# Core API                                                               #
# --------------------------------------------------------------------- #

_MISS = object()  # sentinel so None is a valid cached value


def cache_get(namespace: str, key: str) -> Any:
    """Return cached value or None if miss/expired."""
    ns = _get_or_create(namespace)
    with ns.lock:
        return ns.cache.get(key, _MISS) if False else ns.cache.get(key)
    # Note: cachetools.TTLCache.get returns the default on miss; we use None
    # by convention — callers check `is None` or use the MISS sentinel via
    # cache_get_ex() below.


def cache_get_ex(namespace: str, key: str) -> Tuple[bool, Any]:
    """Return (hit, value). Distinguishes a real None value from a miss."""
    ns = _get_or_create(namespace)
    with ns.lock:
        val = ns.cache.get(key, _MISS)
    if val is _MISS:
        return False, None
    return True, val


def cache_set(namespace: str, key: str, value: Any, ttl: Optional[int] = None) -> None:
    """Store a value. ttl param reserved for future per-entry TTL support
    (cachetools.TTLCache only supports namespace-level TTL; we keep signature
    for forward compatibility)."""
    ns = _get_or_create(namespace)
    with ns.lock:
        ns.cache[key] = value


def invalidate(namespace: str, key: str) -> None:
    """Remove one key from a namespace."""
    ns = _REGISTRY.get(namespace)
    if not ns:
        return
    with ns.lock:
        ns.cache.pop(key, None)


def invalidate_namespace(namespace: str) -> None:
    """Clear an entire namespace (used on bulk writes)."""
    ns = _REGISTRY.get(namespace)
    if not ns:
        return
    with ns.lock:
        ns.cache.clear()


def invalidate_prefix(namespace: str, prefix: str) -> int:
    """Remove all keys in a namespace starting with prefix. Returns count removed.
    Useful for per-user invalidation like invalidate_prefix('visibility', f'{user_id}:')
    """
    ns = _REGISTRY.get(namespace)
    if not ns:
        return 0
    with ns.lock:
        keys = [k for k in ns.cache.keys() if isinstance(k, str) and k.startswith(prefix)]
        for k in keys:
            ns.cache.pop(k, None)
        return len(keys)


def invalidate_contains(namespace: str, substring: str) -> int:
    """Remove all keys in a namespace containing substring. Returns count removed.
    Useful when one entity appears in multiple compound keys."""
    ns = _REGISTRY.get(namespace)
    if not ns:
        return 0
    with ns.lock:
        keys = [k for k in ns.cache.keys() if isinstance(k, str) and substring in k]
        for k in keys:
            ns.cache.pop(k, None)
        return len(keys)


def clear_all() -> None:
    """Nuke everything — for testing or a kill-switch."""
    with _REGISTRY_LOCK:
        for ns in _REGISTRY.values():
            with ns.lock:
                ns.cache.clear()


def cache_stats() -> Dict[str, Dict[str, int]]:
    """Diagnostic snapshot of cache sizes per namespace."""
    out: Dict[str, Dict[str, int]] = {}
    with _REGISTRY_LOCK:
        for name, ns in _REGISTRY.items():
            with ns.lock:
                out[name] = {
                    "size": len(ns.cache),
                    "maxsize": ns.cache.maxsize,
                    "ttl": ns.cache.ttl,
                }
    return out


# --------------------------------------------------------------------- #
# Decorator for pure functions                                           #
# --------------------------------------------------------------------- #

def cached(namespace: str, key_fn: Optional[Callable[..., str]] = None):
    """Cache the result of a pure function.

    By default the key is built from all positional + keyword args; override
    with a custom key_fn(*args, **kwargs) -> str for selective caching.
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if key_fn:
                key = key_fn(*args, **kwargs)
            else:
                key = f"{fn.__name__}:{args}:{sorted(kwargs.items())}"
            hit, val = cache_get_ex(namespace, key)
            if hit:
                return val
            val = fn(*args, **kwargs)
            cache_set(namespace, key, val)
            return val
        return wrapper
    return decorator
