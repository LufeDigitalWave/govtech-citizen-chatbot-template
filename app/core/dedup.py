"""
Redis-based webhook deduplication.

Prevents the same event from being processed twice when:
- The upstream integration retries on timeout.
- Two replicas in a Docker Swarm cluster race on the same message.

Uses SET NX (set-if-not-exists) with an expiry. The first caller that
sets the key owns the event; all subsequent callers within the TTL window
are silently dropped.
"""

from __future__ import annotations

import redis.asyncio as aioredis
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_redis_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """
    Return (or create) the module-level Redis connection pool.

    Called lazily on first dedup check so the app can start even if
    Redis is temporarily unavailable (health check will reflect that).
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


async def is_duplicate(event_id: str, ttl: int = 60) -> bool:
    """
    Check whether this event_id has been seen within the TTL window.

    Uses Redis SET NX EX atomically:
    - First call for a given event_id within `ttl` seconds: sets the key,
      returns False (not a duplicate — proceed with processing).
    - Subsequent calls within `ttl` seconds: key already exists, SET NX
      fails, returns True (duplicate — skip processing).

    Args:
        event_id: Stable unique identifier for this event. For Chatwoot this
                  is the message ID; for Evolution API it is the WhatsApp
                  message key ID.
        ttl:      Seconds to remember the event. Default 60 seconds covers
                  typical webhook retry windows. Increase for slow agents.

    Returns:
        True if the event is a duplicate (already processed or in-flight).
        False if this is the first time we've seen this event_id.
    """
    redis = get_redis()
    key = f"dedup:{event_id}"
    was_set: bool = await redis.set(key, "1", nx=True, ex=ttl)
    # SET NX returns True when the key was set (new), None/False when it existed
    is_dup = not was_set
    if is_dup:
        logger.info("dedup.duplicate_detected", event_id=event_id)
    return is_dup


async def ping_redis() -> bool:
    """
    Health check: attempt a PING to Redis.

    Returns:
        True if Redis is reachable, False otherwise.
    """
    try:
        redis = get_redis()
        await redis.ping()
        return True
    except Exception as exc:
        logger.warning("dedup.redis_ping_failed", error=repr(exc))
        return False
