import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.errors import DomainError
from backend.app.main import create_app
from backend.app.models import DeviceCommand
from tests.support.clock import FixedClock
from tests.support.fixtures_v2 import load_v2_dataset


async def test_two_plans_share_slot_and_retry_precedes_busy_check(tmp_path, fixed_now, monkeypatch):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/race.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "POWER-EQUAL", "plan-slot", 1)
        power = app.state.power
        plans = [await power.preview(str(uuid4()), 45000, "equal", None) for _ in range(2)]
        gate = asyncio.Event()

        async def hold_phase(*args):
            await gate.wait()

        monkeypatch.setattr(power, "_phase", hold_phase)
        ids = [str(uuid4()), str(uuid4())]
        results = await asyncio.gather(
            *(power.execute(identity, plan["plan_id"]) for identity, plan in zip(ids, plans)),
            return_exceptions=True,
        )
        accepted = [i for i, result in enumerate(results) if isinstance(result, dict)]
        assert len(accepted) == 1
        rejected = results[1 - accepted[0]]
        assert isinstance(rejected, DomainError) and rejected.code == "CONTROL_BUSY"
        index = accepted[0]
        assert await power.execute(ids[index], plans[index]["plan_id"]) == results[index]
        assert len(power.tasks) == 1
        gate.set()
        await asyncio.gather(*list(power.tasks.values()))
        assert (await power.get(plans[index]["plan_id"]))["status"] == "VERIFIED"


async def test_unchanged_targets_still_require_fresh_final_feedback(
    tmp_path, fixed_now, monkeypatch
):
    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/stale.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "POWER-EQUAL", "final-fresh", 1)
        power = app.state.power
        plan = await power.preview(str(uuid4()), 45000, "equal", None)
        original_phase = power._phase

        async def age_after_phase(*args):
            await original_phase(*args)
            clock.advance(11)

        monkeypatch.setattr(power, "_phase", age_after_phase)
        async with app.state.db.sessions() as session:
            before = await session.scalar(select(func.count()).select_from(DeviceCommand))
        await power.execute(str(uuid4()), plan["plan_id"])
        await asyncio.gather(*list(power.tasks.values()))
        result = await power.get(plan["plan_id"])
        assert result["status"] == "PARTIAL"
        assert result["results_json"]["error_code"] == "DEVICE_NOT_READY"
        assert (await power.station())["executing_plan_id"] is None
        async with app.state.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(DeviceCommand)) == before
        with pytest.raises(DomainError) as error:
            await power.preview(str(uuid4()), 60000, "equal", None)
        assert error.value.code == "DEVICE_NOT_READY"
