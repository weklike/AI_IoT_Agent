import json
from uuid import uuid4

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.work_orders import WorkOrderService
from tests.support.clock import FixedClock
from tests.support.evidence import seed_hot_run


async def test_work_order_transitions_require_current_recovery_and_cleared_alarm(
    tmp_path, fixed_now, valid_payload
):
    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/orders.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        orders = WorkOrderService(app.state.db, app.state.settings, clock)
        context = await seed_hot_run(app.state.store, valid_payload)
        created = await orders.create("CHG-002", "OVERHEAT", context=context)
        order_id = created["data"]["order_id"]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def transition(version, target, note="", request_id=None):
                return await client.post(
                    f"/api/work-orders/{order_id}/transitions",
                    json={
                        "request_id": request_id or str(uuid4()),
                        "expected_version": version,
                        "target_status": target,
                        "note": note,
                    },
                )

            invalid = await transition(1, "CLOSED")
            assert invalid.status_code == 409, invalid.text
            assert invalid.json()["error"]["code"] == "INVALID_TRANSITION"
            processing = await transition(1, "IN_PROGRESS")
            assert processing.status_code == 200, processing.text
            assert processing.json()["data"]["version"] == 2
            stale = await transition(1, "RESOLVED", "另一请求已修改版本")
            assert stale.status_code == 409
            assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
            unchanged = (await client.get(f"/api/work-orders/{order_id}/events")).json()["data"]
            assert len(unchanged["items"]) == 1
            assert (await transition(2, "RESOLVED", " ")).status_code == 422
            assert (
                await transition(2, "RESOLVED", "已核对模拟温度场景并恢复正常")
            ).status_code == 200
            early = await transition(3, "CLOSED")
            assert (
                early.status_code == 409
                and early.json()["error"]["code"] == "RECOVERY_NOT_CONFIRMED"
            )
            for index in range(6):
                clock.advance(2)
                payload = {
                    **valid_payload,
                    "message_id": str(uuid4()),
                    "seq": 30 + index,
                    "ts": clock.now().isoformat(),
                    "temperature_c": 54,
                }
                await app.state.store.receive(
                    json.dumps(payload).encode(),
                    "charge/v1/devices/CHG-002/telemetry",
                    clock.now(),
                    False,
                )
                if index == 0:
                    assert (await transition(3, "CLOSED")).status_code == 409
            close_request = str(uuid4())
            closed = await transition(3, "CLOSED", request_id=close_request)
            assert closed.status_code == 200, closed.text
            assert closed.json()["data"]["status"] == "CLOSED"
            assert (await transition(3, "CLOSED", request_id=close_request)).json()[
                "data"
            ] == closed.json()["data"]
            events = await client.get(f"/api/work-orders/{order_id}/events")
            assert events.status_code == 200, events.text
            rows = events.json()["data"]["items"]
            assert len(rows) == 3
            recovery = next(row for row in rows if row["to_status"] == "CLOSED")["evidence_json"]
            assert recovery["message_id"] == payload["message_id"]
            assert recovery["device_id"] == "CHG-002"
            clock.advance(2)
            context = await seed_hot_run(
                app.state.store,
                {**valid_payload, "message_id": str(uuid4()), "boot_id": str(uuid4()), "seq": 1},
            )
            new = await orders.create("CHG-002", "OVERHEAT", context=context)
            assert new["data"]["created"] and new["data"]["order_id"] != order_id


async def test_twenty_independent_creates_reuse_in_progress_and_resolved(
    tmp_path, fixed_now, valid_payload
):
    import asyncio

    from sqlalchemy import func, select

    from backend.app.errors import DomainError
    from backend.app.models import WorkOrder

    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/concurrent-orders.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        orders = WorkOrderService(app.state.db, app.state.settings, clock)
        first = await orders.create(
            "CHG-002", "OVERHEAT", context=await seed_hot_run(app.state.store, valid_payload)
        )
        identity = first["data"]["order_id"]
        await orders.transition(identity, str(uuid4()), 1, "IN_PROGRESS", "")
        for status in ("IN_PROGRESS", "RESOLVED"):
            if status == "RESOLVED":
                await orders.transition(
                    identity, str(uuid4()), 2, "RESOLVED", "已处理，等待恢复验证"
                )
            contexts = [await seed_hot_run(app.state.store, valid_payload) for _ in range(20)]
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
            assert all(
                result["data"]["order_id"] == identity
                and result["data"]["status"] == status
                and not result["data"]["created"]
                for result in successes
            )
            async with app.state.db.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(WorkOrder)) == 1


async def test_transition_rollback_keeps_status_event_and_request_atomic(
    tmp_path, fixed_now, valid_payload
):
    import pytest
    from sqlalchemy import event, func, select
    from sqlalchemy.orm import Session

    from backend.app.models import OperationRequest, WorkOrder, WorkOrderEvent

    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/rollback-orders.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        orders = WorkOrderService(app.state.db, app.state.settings, clock)
        created = await orders.create(
            "CHG-002", "OVERHEAT", context=await seed_hot_run(app.state.store, valid_payload)
        )
        identity = created["data"]["order_id"]
        request_id = str(uuid4())

        def fail(session):
            if any(isinstance(row, WorkOrderEvent) for row in session.new):
                raise RuntimeError("injected transition commit failure")

        event.listen(Session, "before_commit", fail)
        try:
            with pytest.raises(RuntimeError, match="injected transition"):
                await orders.transition(identity, request_id, 1, "IN_PROGRESS", "")
        finally:
            event.remove(Session, "before_commit", fail)
        async with app.state.db.sessions() as session:
            row = await session.get(WorkOrder, identity)
            assert (row.status, row.version) == ("OPEN", 1)
            assert await session.scalar(select(func.count()).select_from(WorkOrderEvent)) == 0
            assert await session.get(OperationRequest, request_id) is None
        assert (await orders.transition(identity, request_id, 1, "IN_PROGRESS", ""))[
            "status"
        ] == "IN_PROGRESS"
