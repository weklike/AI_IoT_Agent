from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AlarmEvent
from tests.support.clock import FixedClock


async def test_timeline_stable_late_scoped_bounded_readonly(tmp_path, fixed_now):
    from backend.app.timeline import TimelineService

    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/timeline.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        async with app.state.db.sessions.begin() as session:
            for i in range(105):
                session.add(
                    AlarmEvent(
                        event_id=str(uuid4()),
                        device_id="CHG-001",
                        event_type="triggered",
                        observed_at=fixed_now - timedelta(seconds=10),
                        received_at=fixed_now,
                        evidence_json={"marker": i},
                    )
                )
            session.add(
                AlarmEvent(
                    event_id=str(uuid4()),
                    device_id="CHG-002",
                    event_type="triggered",
                    observed_at=fixed_now,
                    received_at=fixed_now,
                    evidence_json={"foreign": True},
                )
            )
        service = TimelineService(app.state.db)
        first = await service.query("CHG-001", fixed_now - timedelta(minutes=10), fixed_now)
        second = await service.query("CHG-001", fixed_now - timedelta(minutes=10), fixed_now)
        assert first == second
        assert first["event_count"] == 105 and first["truncated"] is True
        assert len(first["items"]) == 100
        assert [item["source_id"] for item in first["items"]] == sorted(
            item["source_id"] for item in first["items"]
        )
        assert all(item["late_received"] for item in first["items"])
        assert all(
            item["source_type"] == "alarm_event" and item["device_id"] == "CHG-001"
            for item in first["items"]
        )
        async with app.state.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(AlarmEvent)) == 106


async def test_tool_event_is_invocation_time_not_synthesized_wall_time(tmp_path, fixed_now):
    from backend.app.timeline import TimelineService

    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/tool-time.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        await app.state.scheduler.reserve_patrol(str(uuid4()), 30)
        await app.state.scheduler.task
        timeline = await TimelineService(app.state.db).query(
            "CHG-001", fixed_now - timedelta(minutes=30), fixed_now
        )
        item = next(row for row in timeline["items"] if row["source_type"] == "tool_call")
        assert item["observed_at"] == item["received_at"] == fixed_now
        assert item["detail"]["event_phase"] == "started"
