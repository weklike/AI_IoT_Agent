import asyncio

import pytest

from backend.app.clocks import DataClock, DeadlineClock
from tests.support.clock import FixedClock


async def test_freezing_data_time_cannot_freeze_deadlines(fixed_now):
    clock = FixedClock(fixed_now)
    deadline = DeadlineClock()
    start = deadline.monotonic()
    clock.advance(86400)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.02):
            await asyncio.sleep(0.1)
    assert 0.015 <= deadline.monotonic() - start < 0.5
    assert clock.now().tzinfo is not None
    assert DataClock().now().utcoffset().total_seconds() == 0
