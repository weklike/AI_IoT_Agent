from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.contracts import TelemetryMessage
from backend.app.db import Database
from backend.app.models import DiagnosticEvent, Telemetry
from backend.app.telemetry.ingest import TelemetryStore
from tests.support.clock import FixedClock


@pytest.fixture
async def store(tmp_path, fixed_now):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
    )
    db = Database(settings)
    clock = FixedClock(fixed_now)
    await db.initialize(clock)
    yield TelemetryStore(db, settings, clock)
    await db.close()


async def test_retransmit_different_received_time(store, valid_payload):
    sample = TelemetryMessage.model_validate(valid_payload)
    assert await store.ingest(sample, store.clock.now()) == "accepted"
    for _ in range(9):
        store.clock.advance(2)
        assert await store.ingest(sample, store.clock.now()) == "duplicate"
    async with store.db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Telemetry)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DiagnosticEvent)
                .where(DiagnosticEvent.event_type == "duplicate")
            )
            == 9
        )
    status = await store.device_status("CHG-002")
    assert status["connection_state"] == "offline"


@pytest.mark.parametrize("key", ["message_id", "sequence"])
async def test_conflict_never_overwrites(store, valid_payload, key):
    sample = TelemetryMessage.model_validate(valid_payload)
    await store.ingest(sample, store.clock.now())
    modified = sample.model_copy(
        update={
            "temperature_c": 30.0,
            **({"message_id": uuid4()} if key == "sequence" else {"seq": 18}),
        }
    )
    assert await store.ingest(modified, store.clock.now()) == "conflict"
    assert (await store.device_status("CHG-002"))["temperature_c"] == 71


async def test_old_and_equal_timestamps_preserve_snapshot(store, valid_payload):
    sample = TelemetryMessage.model_validate(valid_payload)
    await store.ingest(sample, store.clock.now())
    for seq, seconds in [(18, -5), (19, 0)]:
        old = sample.model_copy(
            update={
                "message_id": uuid4(),
                "seq": seq,
                "ts": sample.ts + timedelta(seconds=seconds),
                "temperature_c": 40.0,
            }
        )
        assert await store.ingest(old, store.clock.now()) == "accepted"
    assert (await store.device_status("CHG-002"))["temperature_c"] == 71
    async with store.db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Telemetry)) == 3


@pytest.mark.parametrize(
    "elapsed,connection,fresh",
    [
        (10, "online", True),
        (10.001, "online", False),
        (12, "online", False),
        (15, "online", False),
        (15.001, "offline", False),
    ],
)
async def test_freshness_boundaries(store, valid_payload, elapsed, connection, fresh):
    await store.ingest(TelemetryMessage.model_validate(valid_payload), store.clock.now())
    store.clock.advance(elapsed)
    status = await store.device_status("CHG-002")
    assert status["connection_state"] == connection
    assert status["data_fresh"] is fresh
    assert status["health_state"] == ("overheat" if fresh else "unknown")


async def test_restart_and_replay(store, valid_payload):
    sample = TelemetryMessage.model_validate(valid_payload)
    await store.ingest(sample, store.clock.now())
    await store.db.initialize(store.clock)
    assert (await store.device_status("CHG-002"))["connection_state"] == "unknown"
    assert not (await store.device_status("CHG-002"))["data_fresh"]
    assert await store.ingest(sample, store.clock.now()) == "duplicate"
    store.clock.advance(1)
    new = sample.model_copy(update={"message_id": uuid4(), "seq": 18, "ts": store.clock.now()})
    await store.ingest(new, store.clock.now())
    assert (await store.device_status("CHG-002"))["connection_state"] == "online"


async def test_retained_and_stale_never_mark_online(store, valid_payload):
    sample = TelemetryMessage.model_validate(valid_payload)
    assert await store.ingest(sample, store.clock.now(), retained=True) == "rejected"
    store.clock.advance(11)
    assert await store.ingest(sample, store.clock.now()) == "accepted"
    status = await store.device_status("CHG-002")
    assert status["connection_state"] == "unknown"
    assert status["data_fresh"] is False
    assert status["temperature_c"] == 71


async def test_empty_values_are_null(store):
    status = await store.device_status("CHG-001")
    assert status["connection_state"] == "unknown"
    assert all(status[key] is None for key in ["temperature_c", "sample_ts", "data_age_seconds"])


@pytest.mark.parametrize("offset", [-1, 0])
async def test_old_but_fresh_on_arrival_cannot_extend_live_time(store, valid_payload, offset):
    sample = TelemetryMessage.model_validate(valid_payload)
    await store.ingest(sample, store.clock.now())
    store.clock.advance(2)
    old = sample.model_copy(
        update={"message_id": uuid4(), "seq": 18, "ts": sample.ts + timedelta(seconds=offset)}
    )
    await store.ingest(old, store.clock.now())
    store.clock.advance(13.001)
    assert (await store.device_status("CHG-002"))["connection_state"] == "offline"
