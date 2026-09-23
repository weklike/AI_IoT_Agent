import asyncio
from datetime import timedelta
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


async def test_unknown_command_upper_bound_blocks_new_plan(tmp_path, fixed_now):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/unknown.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "POWER-EQUAL", "unknown-upper-bound", 1)
        async with app.state.db.sessions.begin() as session:
            session.add(
                DeviceCommand(
                    command_id=str(uuid4()),
                    device_id="CHG-001",
                    generation=100,
                    action="set_power_limit",
                    args_json={"power_limit_w": 20000},
                    status="timed_out",
                    verification_status="unconfirmed",
                    issued_at=fixed_now - timedelta(seconds=10),
                    expires_at=fixed_now - timedelta(seconds=5),
                )
            )
        with pytest.raises(DomainError) as error:
            await app.state.power.preview(str(uuid4()), 60000, "equal", None)
        assert error.value.code == "DEVICE_NOT_READY"
        assert not app.state.power.tasks


async def test_stop_between_phases_prevents_all_later_increases(tmp_path, fixed_now, monkeypatch):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/stop.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "POWER-EQUAL", "stop-between-phases", 1)
        power = app.state.power
        plan = await power.preview(
            str(uuid4()), 45000, "priority", ["CHG-002", "CHG-001", "CHG-003"]
        )
        lower_entered, release = asyncio.Event(), asyncio.Event()
        original = power._phase
        phase_count = 0

        async def hold_lower(plan_id, targets):
            nonlocal phase_count
            phase_count += 1
            if phase_count == 1:
                assert targets == {"CHG-003": 5000}
                lower_entered.set()
                await release.wait()
            else:
                await original(plan_id, targets)

        class Publisher:
            connected = True
            calls = []

            def publish(self, topic, payload):
                self.calls.append(payload)
                return True

        publisher = Publisher()
        monkeypatch.setattr(app.state.charging, "mqtt", publisher)
        monkeypatch.setattr(power, "_phase", hold_lower)
        await power.execute(str(uuid4()), plan["plan_id"])
        await asyncio.wait_for(lower_entered.wait(), 2)
        state = await app.state.store.device_status("CHG-001")
        await app.state.charging.create(
            "CHG-001", str(uuid4()), "stop_session", {"session_id": state["session_id"]}
        )
        release.set()
        await asyncio.gather(*list(power.tasks.values()))
        result = await power.get(plan["plan_id"])
        assert result["status"] == "PARTIAL"
        assert len(publisher.calls) == 1
        assert '"action":"stop_session"' in publisher.calls[0]
        assert not result["commands"]
