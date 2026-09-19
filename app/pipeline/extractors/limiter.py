import logging
import threading
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_local_semaphore: threading.Semaphore | None = None
_local_lock = threading.Lock()


def _get_local_semaphore(max_concurrency: int) -> threading.Semaphore:
    global _local_semaphore
    with _local_lock:
        if _local_semaphore is None:
            _local_semaphore = threading.Semaphore(max_concurrency)
        return _local_semaphore


@contextmanager
def acquire_llm_slot(timeout_s: float = 30.0) -> Generator[None, None, None]:
    """Acquires a concurrency slot for an LLM call using Redis or local semaphore."""
    settings = get_settings()
    max_concurrency = max(1, settings.llm_max_concurrency)

    client: redis.Redis | None = None
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            decode_responses=True,
        )
        client.ping()
    except Exception:
        client = None

    if client is None:
        sem = _get_local_semaphore(max_concurrency)
        acquired = sem.acquire(timeout=timeout_s)
        if not acquired:
            logger.warning("Local LLM concurrency limit reached; proceeding anyway")
        try:
            yield
        finally:
            if acquired:
                sem.release()
        return

    token = str(uuid.uuid4())
    zset_key = "llm:active_slots"
    slot_ttl = max(60.0, float(settings.llm_timeout_s * 2))
    start_time = time.time()
    acquired = False

    try:
        while time.time() - start_time < timeout_s:
            now = time.time()
            pipe = client.pipeline()
            # Clear expired slots older than slot_ttl
            pipe.zremrangebyscore(zset_key, "-inf", now - slot_ttl)
            pipe.zcard(zset_key)
            results = pipe.execute()
            current_active = results[1]

            if current_active < max_concurrency:
                # Slot available, add token with timestamp
                client.zadd(zset_key, {token: now})
                acquired = True
                break
            time.sleep(0.5)

        if not acquired:
            logger.warning(
                "Timed out waiting for LLM concurrency slot (%d active), proceeding anyway",
                max_concurrency,
            )

        yield
    finally:
        if acquired and client is not None:
            try:
                client.zrem(zset_key, token)
            except Exception as e:
                logger.debug("Failed to release LLM slot in Redis: %s", e)
