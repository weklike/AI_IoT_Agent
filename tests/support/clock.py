from datetime import datetime, timedelta

from backend.app.clocks import DataClock


class FixedClock(DataClock):
    def __init__(self, now: datetime):
        self.value = now

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += timedelta(seconds=seconds)
