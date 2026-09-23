from uuid import uuid4

from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DeviceCommand, PowerPlan, StationState
from tests.support.clock import FixedClock
from tests.support.fixtures_v2 import load_v2_dataset


async def test_restart_interrupts_persisted_executing_plan_without_replaying_commands(
    tmp_path, fixed_now
):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/restart.db",
    )
    clock = FixedClock(fixed_now)
    app = create_app(settings, clock=clock)
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "POWER-EQUAL", "plan-restart", 1)
        created = await app.state.power.preview(
            str(uuid4()), 45000, "priority", ["CHG-002", "CHG-001", "CHG-003"]
        )
        async with app.state.db.sessions.begin() as session:
            # Reproduce the durable reservation at an abrupt process exit, before dispatch.
            plan = await session.get(PowerPlan, created["plan_id"])
            plan.status = "EXECUTING"
            station = await session.get(StationState, 1)
            station.executing_plan_id = plan.plan_id
            before = await session.scalar(select(func.count()).select_from(DeviceCommand))
    restarted = create_app(settings, clock=clock)
    async with restarted.router.lifespan_context(restarted):
        plan = await restarted.state.power.get(created["plan_id"])
        assert plan["status"] == "INTERRUPTED"
        assert (await restarted.state.power.station())["executing_plan_id"] is None
        assert restarted.state.power.tasks == {} and restarted.state.charging.tasks == {}
        async with restarted.state.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(DeviceCommand)) == before
