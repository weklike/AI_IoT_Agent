import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from backend.app.config import Settings
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import ToolCall, WorkOrder
from backend.app.telemetry.ingest import TelemetryStore
from backend.app.work_orders import WorkOrderService
from tests.support.clock import FixedClock
from tests.support.evidence import seed_hot_run


@pytest.fixture
async def services(tmp_path, fixed_now):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
    )
    db, clock = Database(settings), FixedClock(fixed_now)
    await db.initialize(clock)
    store = TelemetryStore(db, settings, clock)
    yield store, WorkOrderService(db, settings, clock)
    await db.close()


async def test_authorization_denied(services, valid_payload):
    store, orders = services
    context = await seed_hot_run(store, valid_payload, allowed=False)
    with pytest.raises(DomainError, match="授权") as error:
        await orders.create("CHG-002", "OVERHEAT", context=context)
    assert error.value.code == "WRITE_NOT_ALLOWED"
    async with store.db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(WorkOrder)) == 0


@pytest.mark.parametrize("mutation", ["other_run", "other_device", "normal", "expired"])
async def test_invalid_evidence(services, valid_payload, mutation):
    store, orders = services
    if mutation == "normal":
        valid_payload["temperature_c"] = 38
    context = await seed_hot_run(store, valid_payload)
    if mutation == "expired":
        store.clock.advance(11)
    if mutation in {"other_run", "other_device"}:
        async with store.db.sessions.begin() as session:
            if mutation == "other_run":
                await session.execute(
                    update(ToolCall)
                    .where(ToolCall.tool_name == "get_device_status")
                    .values(status="failed")
                )
            else:
                await session.execute(
                    update(ToolCall)
                    .where(ToolCall.tool_name == "get_device_status")
                    .values(args_json={"device_id": "CHG-001"})
                )
    with pytest.raises(DomainError) as error:
        await orders.create("CHG-002", "OVERHEAT", context=context)
    assert error.value.code == "INVALID_EVIDENCE"


async def test_20_concurrent_independent_transactions(services, valid_payload):
    store, orders = services
    contexts = [await seed_hot_run(store, valid_payload) for _ in range(20)]
    results = await asyncio.gather(
        *(orders.create("CHG-002", "OVERHEAT", context=context) for context in contexts),
        return_exceptions=True,
    )
    successes = [result for result in results if isinstance(result, dict)]
    assert successes
    assert all(
        isinstance(result, dict)
        or isinstance(result, DomainError)
        and result.code == "DATABASE_BUSY"
        for result in results
    )
    assert len({result["data"]["order_id"] for result in successes}) == 1
    assert sum(result["data"]["created"] for result in successes) == 1
    async with store.db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(WorkOrder)) == 1
        order = await session.scalar(select(WorkOrder))
        assert order.evidence_json["tool_call_id"]
        assert order.evidence_json["samples"][0]["message_id"] == valid_payload["message_id"]
        for context, result in zip(contexts, results):
            if isinstance(result, dict):
                row = await session.get(ToolCall, str(context.tool_call_id))
                assert row.result_json == result


async def test_result_and_order_roll_back_together(services, valid_payload):
    store, orders = services
    context = await seed_hot_run(store, valid_payload)
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    def interrupt(session):
        raise asyncio.CancelledError()

    event.listen(Session, "before_commit", interrupt)
    try:
        with pytest.raises(asyncio.CancelledError):
            await orders.create("CHG-002", "OVERHEAT", context=context)
    finally:
        event.remove(Session, "before_commit", interrupt)
    async with store.db.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(WorkOrder)) == 0
        assert (await session.get(ToolCall, str(context.tool_call_id))).result_json is None


async def test_evidence_must_belong_to_current_run(services, valid_payload):
    from backend.app.contracts import ToolContext

    store, orders = services
    first = await seed_hot_run(store, valid_payload)
    second = await seed_hot_run(store, valid_payload)
    async with store.db.sessions.begin() as session:
        await session.execute(
            update(ToolCall)
            .where(ToolCall.run_id == str(second.run_id), ToolCall.tool_name == "get_device_status")
            .values(status="failed")
        )
    with pytest.raises(DomainError) as error:
        await orders.create("CHG-002", "OVERHEAT", context=second)
    assert error.value.code == "INVALID_EVIDENCE"
    forged = ToolContext(
        run_id=first.run_id, tool_call_id=second.tool_call_id, allow_work_order=True
    )
    with pytest.raises(DomainError) as error:
        await orders.create("CHG-002", "OVERHEAT", context=forged)
    assert error.value.code == "INVALID_EVIDENCE"


async def test_offline_evidence_is_rechecked_after_recovery(services, valid_payload):
    from backend.app.api import json_data
    from backend.app.contracts import TelemetryMessage

    store, orders = services
    context = await seed_hot_run(store, valid_payload)
    store.clock.advance(16)
    offline = await store.device_status("CHG-002")
    async with store.db.sessions.begin() as session:
        await session.execute(
            update(ToolCall)
            .where(ToolCall.tool_call_id == str(context.tool_call_id))
            .values(args_json={"device_id": "CHG-002", "reason_code": "OFFLINE"})
        )
        read = await session.scalar(
            select(ToolCall).where(
                ToolCall.run_id == str(context.run_id), ToolCall.tool_name == "get_device_status"
            )
        )
        read.result_json = {
            "tool_call_id": read.tool_call_id,
            "ok": True,
            "data": json_data(offline),
            "error": None,
        }
    await store.ingest(
        TelemetryMessage.model_validate(
            {**valid_payload, "message_id": str(uuid4()), "seq": 18, "ts": store.clock.now()}
        ),
        store.clock.now(),
    )
    with pytest.raises(DomainError) as error:
        await orders.create("CHG-002", "OFFLINE", context=context)
    assert error.value.code == "INVALID_EVIDENCE"


async def test_historical_hot_sample_and_index(services, valid_payload):
    from sqlalchemy.exc import IntegrityError

    from backend.app.api import json_data

    store, orders = services
    context = await seed_hot_run(store, valid_payload)
    store.clock.advance(300)
    history = await store.history("CHG-002", 10)
    async with store.db.sessions.begin() as session:
        read = await session.scalar(
            select(ToolCall).where(
                ToolCall.run_id == str(context.run_id), ToolCall.tool_name == "get_device_status"
            )
        )
        read.tool_name = "get_device_history"
        read.result_json = {
            "tool_call_id": read.tool_call_id,
            "ok": True,
            "data": json_data(history),
            "error": None,
        }
    created = await orders.create("CHG-002", "OVERHEAT", context=context)
    assert created["data"]["created"]
    with pytest.raises(IntegrityError):
        async with store.db.sessions.begin() as session:
            session.add(
                WorkOrder(
                    order_id=str(uuid4()),
                    device_id="CHG-002",
                    reason_code="OVERHEAT",
                    status="OPEN",
                    evidence_json={},
                    created_from_run_id=str(context.run_id),
                    created_at=store.clock.now(),
                )
            )


async def test_reused_order_retains_this_calls_selected_evidence(services, valid_payload):
    store, orders = services
    first = await seed_hot_run(store, valid_payload)
    second = await seed_hot_run(store, valid_payload)
    await orders.create("CHG-002", "OVERHEAT", context=first)
    result = await orders.create("CHG-002", "OVERHEAT", context=second)
    assert result["data"]["created"] is False
    assert result["data"]["evidence"]["run_id"] == str(second.run_id)
    async with store.db.sessions() as session:
        saved = await session.get(ToolCall, str(second.tool_call_id))
        assert saved.result_json["data"]["evidence"] == result["data"]["evidence"]


async def test_sqlite_busy_timeout_is_explicit_and_bounded(services, valid_payload):
    import time

    from sqlalchemy import text

    store, orders = services
    context = await seed_hot_run(store, valid_payload)
    async with store.db.engine.connect() as locked:
        await locked.execute(text("BEGIN IMMEDIATE"))
        started = time.monotonic()
        with pytest.raises(DomainError) as error:
            await orders.create("CHG-002", "OVERHEAT", context=context)
        elapsed = time.monotonic() - started
        assert error.value.code == "DATABASE_BUSY"
        assert 0.95 <= elapsed < 1.5
        await locked.rollback()
