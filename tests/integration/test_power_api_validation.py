from uuid import uuid4

import httpx
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DeviceCommand, StationState
from tests.support.clock import FixedClock
from tests.support.fixtures_v2 import load_v2_dataset


async def test_power_api_rejects_invalid_allocations_and_changed_station_revision(
    tmp_path, fixed_now
):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/power-validation.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "POWER-EQUAL", "power-api-validation", 1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for changes in [
                {"budget_w": True},
                {"budget_w": "45000"},
                {"budget_w": 45101},
                {"budget_w": 60100},
                {"budget_w": -100},
                {"strategy": "unknown"},
                {"strategy": "priority", "device_priority": ["CHG-001"] * 3},
            ]:
                response = await client.post(
                    "/api/power-plans",
                    json={
                        "request_id": str(uuid4()),
                        "budget_w": 45000,
                        "strategy": "equal",
                        **changes,
                    },
                )
                assert response.status_code == 422, response.text
            response = await client.post(
                "/api/power-plans",
                json={"request_id": str(uuid4()), "budget_w": 45000, "strategy": "equal"},
            )
            assert response.status_code == 201
            plan = response.json()["data"]["plan_id"]
            async with app.state.db.sessions.begin() as session:
                station = await session.get(StationState, 1)
                station.revision += 1
                before = await session.scalar(select(func.count()).select_from(DeviceCommand))
            response = await client.post(
                f"/api/power-plans/{plan}/execute", json={"request_id": str(uuid4())}
            )
            assert response.status_code == 409 and response.json()["error"]["code"] == "PLAN_STALE"
            async with app.state.db.sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(DeviceCommand)) == before
                )
