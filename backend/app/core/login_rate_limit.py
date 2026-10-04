from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


class LoginRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self._events = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, now: datetime) -> RateLimitDecision:
        cutoff = now - timedelta(seconds=self.window_seconds)
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry = max(
                    1,
                    int((events[0] + timedelta(seconds=self.window_seconds) - now).total_seconds())
                    + 1,
                )
                return RateLimitDecision(False, retry)
            events.append(now)
            if not events:
                self._events.pop(key, None)
            return RateLimitDecision(True)
