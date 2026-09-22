import time
from datetime import UTC, datetime


class DataClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class DeadlineClock:
    def monotonic(self) -> float:
        return time.monotonic()
