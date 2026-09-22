import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from backend.app.errors import DomainError
from backend.app.models import Device, OperationRequest
from tests.integration.test_migrations import database


async def test_operation_idempotency_conflict_and_rollback(tmp_path, fixed_now):
    from backend.app.operations import execute_operation

    db = database(tmp_path / "ops.db")
    await db.initialize()
    calls = 0

    async def change(session):
        nonlocal calls
        calls += 1
        await session.execute(text("UPDATE devices SET name='changed' WHERE device_id='CHG-001'"))
        return {"device_id": "CHG-001"}

    async def invoke(request_id, route="/devices/CHG-001/start", args=None, callback=change):
        async with db.sessions() as session:
            return await execute_operation(
                session,
                request_id=request_id,
                route=route,
                action="start",
                parameters=args or {"power": 1000},
                now=fixed_now,
                perform=callback,
            )

    try:
        request_id = str(uuid4())
        results = await asyncio.gather(*(invoke(request_id) for _ in range(5)))
        assert results == [{"device_id": "CHG-001"}] * 5
        assert calls == 1
        for change_args in ({"route": "/devices/CHG-002/start"}, {"args": {"power": 2000}}):
            with pytest.raises(DomainError) as error:
                await invoke(request_id, **change_args)
            assert (error.value.code, error.value.status) == ("REQUEST_CONFLICT", 409)

        async def fail(session):
            await session.execute(text("UPDATE devices SET name='bad' WHERE device_id='CHG-001'"))
            raise DomainError("CONTROL_BUSY", "busy", 409)

        with pytest.raises(DomainError):
            await invoke(str(uuid4()), callback=fail)
        async with db.sessions() as session:
            assert len((await session.scalars(select(OperationRequest))).all()) == 1
            assert (await session.get(Device, "CHG-001")).name == "changed"
    finally:
        await db.close()
