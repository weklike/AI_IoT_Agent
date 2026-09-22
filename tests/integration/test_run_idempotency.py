import asyncio
from uuid import uuid4

import pytest

from backend.app.agent.scheduler import RunScheduler
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.errors import DomainError


async def test_reservation_idempotency_precedes_slot(tmp_path):
    db = Database(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        )
    )
    await db.initialize()
    started = []
    gate = asyncio.Event()

    async def execute(run_id):
        started.append(run_id)
        await gate.wait()

    scheduler = RunScheduler(db, DataClock(), execute)
    key = str(uuid4())
    try:
        results = await asyncio.gather(
            *(scheduler.reserve(key, "查询2号桩", False) for _ in range(5))
        )
        assert len(set(results)) == 1
        await asyncio.sleep(0)
        assert len(started) == 1
        assert await scheduler.reserve(key, "查询2号桩", False) == results[0]
        with pytest.raises(DomainError) as error:
            await scheduler.reserve(key, "不同问题", False)
        assert error.value.status == 409
        with pytest.raises(DomainError) as error:
            await scheduler.reserve(str(uuid4()), "另一个任务", False)
        assert error.value.status == 429
        gate.set()
        await scheduler.task
        assert await scheduler.reserve(key, "查询2号桩", False) == results[0]
        gate.clear()
        simultaneous = await asyncio.gather(
            *(scheduler.reserve(str(uuid4()), "新任务", False) for _ in range(2)),
            return_exceptions=True,
        )
        assert sum(isinstance(value, str) for value in simultaneous) == 1
        assert (
            sum(
                isinstance(value, DomainError) and value.code == "AGENT_BUSY"
                for value in simultaneous
            )
            == 1
        )
    finally:
        await scheduler.close()
        await db.close()


async def test_http_concurrency_and_retries(tmp_path):
    import httpx

    from backend.app.main import create_app

    gate = asyncio.Event()
    accepted = []

    async def execute(run_id):
        accepted.append(run_id)
        await gate.wait()

    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/http.db",
        ),
        run_executor=execute,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            bodies = [{"request_id": str(uuid4()), "question": "查状态"} for _ in range(2)]
            results = await asyncio.gather(
                *(client.post("/api/agent/runs", json=body) for body in bodies)
            )
            assert sorted(response.status_code for response in results) == [202, 429]
            index = next(i for i, response in enumerate(results) if response.status_code == 202)
            again = await client.post("/api/agent/runs", json=bodies[index])
            assert again.json()["data"]["run_id"] == results[index].json()["data"]["run_id"]
            assert len(accepted) == 1
            changed = await client.post(
                "/api/agent/runs", json={**bodies[index], "allow_work_order": True}
            )
            assert changed.status_code == 409
            invalid = await client.post(
                "/api/agent/runs", json={"request_id": str(uuid4()), "question": " "}
            )
            assert invalid.status_code == 422
            assert (await client.get("/api/work-orders")).json()["data"] == []
