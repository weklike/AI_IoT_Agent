import json

from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Alarm
from tests.support.clock import FixedClock


async def test_offline_alarm_strict_fifteen_second_boundary_and_unknown_devices(
    tmp_path, fixed_now, valid_payload
):
    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/boundary.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):

        async def offline_alarms():
            async with app.state.db.sessions() as session:
                return list(
                    (
                        await session.scalars(select(Alarm).where(Alarm.reason_code == "OFFLINE"))
                    ).all()
                )

        await app.state.alarms.evaluate_time()
        assert await offline_alarms() == []
        assert (
            await app.state.store.receive(
                json.dumps(valid_payload).encode(),
                "charge/v1/devices/CHG-002/telemetry",
                clock.now(),
                False,
            )
            == "accepted"
        )
        clock.advance(15)
        await app.state.alarms.evaluate_time()
        assert await offline_alarms() == []
        clock.advance(0.001)
        await app.state.alarms.evaluate_time()
        rows = await offline_alarms()
        assert len(rows) == 1 and rows[0].device_id == "CHG-002"
        assert rows[0].condition == "ACTIVE"
        await app.state.alarms.evaluate_time()
        assert [r.alarm_id for r in await offline_alarms()] == [rows[0].alarm_id]
