from datetime import datetime
from typing import Protocol

from app.db.utc import utc_now


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utc_now()
