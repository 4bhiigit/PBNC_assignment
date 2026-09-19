import time
from collections import defaultdict

from redis.asyncio import from_url as async_redis_from_url

from app.config import get_settings
from app.errors import RateLimitedException

# In-memory sliding window fallback for unit tests and offline environments
_memory_windows: dict[str, list[float]] = defaultdict(list)


async def check_rate_limit(
    identifier: str,
    action: str = "upload",
    max_requests: int = 10,
    window_seconds: int = 60,
) -> None:
    """Performs rate-limiting check on the given identifier (e.g. user_id).
    Uses Redis sliding log if available; falls back gracefully to in-memory tracking.
    """
    settings = get_settings()
    rate_key = f"ratelimit:{action}:{identifier}"
    now = time.time()

    # Try Redis first
    try:
        redis_client = async_redis_from_url(
            settings.redis_url, socket_timeout=1.0, socket_connect_timeout=1.0
        )
        pipe = redis_client.pipeline()
        # Remove timestamps outside the current window
        pipe.zremrangebyscore(rate_key, 0, now - window_seconds)
        # Add current request timestamp
        pipe.zadd(rate_key, {str(now): now})
        # Count requests in window
        pipe.zcard(rate_key)
        pipe.expire(rate_key, window_seconds)
        results = await pipe.execute()
        await redis_client.aclose()

        current_count = results[2]
        if current_count > max_requests:
            raise RateLimitedException(
                f"Rate limit exceeded: maximum {max_requests} requests per {window_seconds}s"
            )
        return
    except RateLimitedException:
        raise
    except Exception:
        # Fall back to in-memory sliding window
        pass

    window = _memory_windows[rate_key]
    cutoff = now - window_seconds
    _memory_windows[rate_key] = [t for t in window if t > cutoff]

    if len(_memory_windows[rate_key]) >= max_requests:
        raise RateLimitedException(
            f"Rate limit exceeded: maximum {max_requests} requests per {window_seconds}s"
        )

    _memory_windows[rate_key].append(now)
