from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass


class SessionLockRegistry:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def discard_if_idle(self, key: str) -> None:
        lock = self._locks.get(key)
        if lock is not None and not lock.locked():
            self._locks.pop(key, None)


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


class PublicChatRateLimiter:
    """In-memory token bucket. Keys are digests, never raw network addresses."""

    def __init__(self, per_minute: int, burst: int) -> None:
        self.per_minute = max(1, per_minute)
        self.burst = max(1, burst)
        self._buckets: dict[str, _Bucket] = {}

    def check(self, key: str) -> int | None:
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = _Bucket(tokens=float(self.burst), updated_at=now)
            self._buckets[key] = bucket
        elapsed = max(0.0, now - bucket.updated_at)
        refill_per_second = self.per_minute / 60.0
        bucket.tokens = min(float(self.burst), bucket.tokens + elapsed * refill_per_second)
        bucket.updated_at = now
        if bucket.tokens < 1.0:
            return max(1, math.ceil((1.0 - bucket.tokens) / refill_per_second))
        bucket.tokens -= 1.0
        return None
