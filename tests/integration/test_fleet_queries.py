from datetime import timedelta
from uuid import uuid4

from sqlalchemy import insert

from backend.app.agent.read_queries import ReadQueries
from backend.app.config import Settings
from backend.app.contracts import TelemetryMessage
from backend.app.main import create_app
from backend.app.models import Telemetry
from tests.support.clock import FixedClock


async def test_fleet_keeps_empty_devices_and_aggregates_more_than_display_limit(
    tmp_path, fixed_now, valid_payload
):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/fleet.db",
    )
    clock = FixedClock(fixed_now)
    app = create_app(settings, clock=clock)
    async with app.router.lifespan_context(app):
        await app.state.store.ingest(TelemetryMessage.model_validate(valid_payload), fixed_now)
        async with app.state.db.sessions.begin() as session:
            await session.execute(
                insert(Telemetry),
                [
                    dict(
                        device_id="CHG-002",
                        message_id=str(uuid4()),
                        boot_id=str(uuid4()),
                        seq=i,
                        ts=fixed_now - timedelta(seconds=1),
                        received_at=fixed_now,
                        temperature_c=40.0,
                        voltage_v=400.0,
                        current_a=50.0,
                        power_kw=20.0,
                        operating_state="charging",
                        schema_version=1,
                    )
                    for i in range(5001)
                ],
            )
        queries = ReadQueries(app.state.db, settings, clock)
        result = await queries.fleet(10)
        assert result["to"] == fixed_now
        assert len(result["devices"]) == 3
        empty, active = result["devices"][:2]
        assert empty["status"]["connection_state"] == "unknown"
        assert empty["statistics"]["sample_count"] == 0
        assert empty["statistics"]["temperature_avg_c"] is None
        assert active["statistics"]["sample_count"] == 5002
        assert active["statistics"]["overheat_count"] == 1
        assert active["statistics"]["temperature_max_c"] == 71
        assert result["latest_plan"] is None
        assert active["charging_statistics"]["completed_session_energy_wh"] is None
        assert (await queries.sessions("CHG-001", 10))["items"] == []
        assert (await queries.work_orders("CHG-001"))["truncated"] is False


async def test_readonly_tools_bound_rows_without_truncating_counts(tmp_path, fixed_now):
    from backend.app.models import AgentRun, ChargingSession, WorkOrder

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/bounded.db",
    )
    app = create_app(settings, clock=FixedClock(fixed_now))
    async with app.router.lifespan_context(app):
        async with app.state.db.sessions.begin() as session:
            run_id = str(uuid4())
            session.add(
                AgentRun(
                    run_id=run_id,
                    request_id=str(uuid4()),
                    request_hash="seed",
                    question="seed",
                    status="completed",
                    created_at=fixed_now,
                )
            )
            await session.flush()
            for i in range(25):
                session.add(
                    ChargingSession(
                        session_id=str(uuid4()),
                        device_id="CHG-001",
                        status="COMPLETED",
                        requested_power_w=1000,
                        started_at=fixed_now - timedelta(minutes=5),
                        ended_at=fixed_now - timedelta(seconds=i),
                        observed_at=fixed_now,
                        start_meter_wh=i * 10,
                        end_meter_wh=i * 10 + 10,
                        energy_wh=10,
                        report_seq=2,
                    )
                )
                session.add(
                    WorkOrder(
                        order_id=str(uuid4()),
                        device_id="CHG-001",
                        reason_code="OVERHEAT",
                        status="CLOSED",
                        evidence_json={},
                        created_from_run_id=run_id,
                        created_at=fixed_now - timedelta(minutes=2),
                        closed_at=fixed_now - timedelta(seconds=i),
                    )
                )
            for reason, state in [("OVERHEAT", "IN_PROGRESS"), ("OFFLINE", "RESOLVED")]:
                session.add(
                    WorkOrder(
                        order_id=str(uuid4()),
                        device_id="CHG-001",
                        reason_code=reason,
                        status=state,
                        evidence_json={},
                        created_from_run_id=run_id,
                        created_at=fixed_now,
                    )
                )
        queries = app.state.read_queries
        sessions = await queries.sessions("CHG-001", 10)
        assert len(sessions["items"]) == 20 and sessions["truncated"] is True
        assert sessions["summary"]["session_count"] == 25
        assert sessions["summary"]["completed_session_energy_wh"] == 250
        orders = await queries.work_orders("CHG-001")
        assert len(orders["closed"]) == 20 and orders["truncated"] is True
        assert orders["closed_count"] == 25
        assert {row["status"] for row in orders["unclosed"]} == {"IN_PROGRESS", "RESOLVED"}
        assert (await queries.work_orders("CHG-003"))["closed_count"] == 0
