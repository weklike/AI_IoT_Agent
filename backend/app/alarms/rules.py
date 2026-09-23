from datetime import datetime
from typing import TypedDict


class DurationState(TypedDict):
    last_ts: str
    start_ts: str | None


def observe_duration(
    previous: DurationState | None,
    sample_ts: datetime,
    condition: bool,
    required_seconds: int,
    max_gap_seconds: float = 3,
) -> tuple[DurationState, bool]:
    last = datetime.fromisoformat(previous["last_ts"]) if previous else None
    if last is not None and sample_ts == last:
        return previous, False
    if last is not None and sample_ts < last:
        return {"last_ts": last.isoformat(), "start_ts": None}, False
    start = None
    if condition:
        contiguous = last is not None and (sample_ts - last).total_seconds() <= max_gap_seconds
        start = (
            datetime.fromisoformat(previous["start_ts"])
            if contiguous and previous["start_ts"]
            else sample_ts
        )
    state = {"last_ts": sample_ts.isoformat(), "start_ts": start.isoformat() if start else None}
    return state, start is not None and (sample_ts - start).total_seconds() >= required_seconds
