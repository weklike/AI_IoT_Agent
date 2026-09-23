from uuid import uuid4

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AgentRun, WorkOrder
from tests.support.clock import FixedClock


async def test_run_history_and_work_order_pages_keep_legacy_array(tmp_path, fixed_now):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/lists.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        ids = [str(uuid4()) for _ in range(3)]
        async with app.state.db.sessions.begin() as session:
            for identifier in ids:
                session.add(
                    AgentRun(
                        run_id=identifier,
                        request_id=str(uuid4()),
                        request_hash="seed",
                        question="历史任务",
                        status="completed",
                        created_at=fixed_now,
                    )
                )
            await session.flush()
            for i in range(3):
                session.add(
                    WorkOrder(
                        order_id=str(uuid4()),
                        device_id="CHG-001",
                        reason_code="OVERHEAT",
                        status="CLOSED",
                        created_from_run_id=ids[i],
                        created_at=fixed_now,
                        closed_at=fixed_now,
                        evidence_json={},
                    )
                )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for path, key in [("/api/agent/runs", "run_id"), ("/api/work-orders", "order_id")]:
                first = (await client.get(path, params={"limit": 2})).json()["data"]
                assert len(first["items"]) == 2
                second = (
                    await client.get(path, params={"limit": 2, "cursor": first["next_cursor"]})
                ).json()["data"]
                assert len(second["items"]) == 1 and second["next_cursor"] is None
                assert len({item[key] for item in first["items"] + second["items"]}) == 3
            assert len((await client.get("/api/work-orders")).json()["data"]) == 3
            assert (
                await client.get("/api/work-orders", params={"limit": 2, "state": "UNCLOSED"})
            ).json()["data"]["items"] == []
