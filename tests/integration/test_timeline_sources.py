from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import (
    AgentRun,
    AlarmEvent,
    ChargingSession,
    DeviceCommand,
    OperationRequest,
    ScenarioCommandRow,
    SessionReport,
    ToolCall,
    WorkOrder,
    WorkOrderEvent,
)
from backend.app.timeline import TimelineService
from tests.support.clock import FixedClock


async def test_all_event_sources_link_exact_records_and_keep_late_receipts(tmp_path, fixed_now):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/sources.db",
        ),
        clock=FixedClock(fixed_now),
    )
    observed = fixed_now - timedelta(seconds=20)
    async with app.router.lifespan_context(app):
        run_id, session_id, order_id, request_id = [str(uuid4()) for _ in range(4)]
        async with app.state.db.sessions.begin() as session:
            session.add(
                AgentRun(
                    run_id=run_id,
                    request_id=str(uuid4()),
                    request_hash="seed",
                    question="seed",
                    status="completed",
                    created_at=observed,
                )
            )
            session.add(
                ChargingSession(
                    session_id=session_id,
                    device_id="CHG-001",
                    status="COMPLETED",
                    requested_power_w=1000,
                    started_at=observed,
                    observed_at=observed,
                    ended_at=observed,
                )
            )
            session.add(
                OperationRequest(
                    request_id=request_id,
                    request_hash="seed",
                    route="/seed",
                    action="seed",
                    result_json={},
                    created_at=observed,
                )
            )
            await session.flush()
            session.add(
                WorkOrder(
                    order_id=order_id,
                    device_id="CHG-001",
                    reason_code="OVERHEAT",
                    status="IN_PROGRESS",
                    evidence_json={},
                    created_from_run_id=run_id,
                    created_at=observed,
                )
            )
            await session.flush()
            session.add(
                WorkOrderEvent(
                    event_id=str(uuid4()),
                    order_id=order_id,
                    request_id=request_id,
                    from_status="OPEN",
                    to_status="IN_PROGRESS",
                    note="现场核查",
                    checked_at=observed,
                    evidence_json={"fact": 1},
                )
            )
            session.add(
                SessionReport(
                    report_id=str(uuid4()),
                    session_id=session_id,
                    report_seq=1,
                    payload_json={"session_id": session_id},
                    observed_at=observed,
                    received_at=fixed_now,
                )
            )
            session.add(
                AlarmEvent(
                    event_id=str(uuid4()),
                    device_id="CHG-001",
                    event_type="triggered",
                    observed_at=observed,
                    received_at=fixed_now,
                    evidence_json={"sample": "actual"},
                )
            )
            session.add(
                DeviceCommand(
                    command_id=str(uuid4()),
                    device_id="CHG-001",
                    generation=1,
                    action="set_limit",
                    args_json={"power_limit_w": 0},
                    status="applied",
                    issued_at=observed,
                    expires_at=observed + timedelta(seconds=5),
                    ack_at=fixed_now,
                    ack_observed_at=observed,
                    ack_json={"status": "applied"},
                    late_ack_observed_at=observed,
                    late_ack_received_at=fixed_now,
                    late_ack_json={"status": "applied"},
                )
            )
            session.add(
                ScenarioCommandRow(
                    command_id=str(uuid4()),
                    device_id="CHG-001",
                    scenario="normal",
                    status="applied",
                    requested_at=observed,
                    ack_at=observed,
                    ack_received_at=fixed_now,
                    late_ack_observed_at=observed,
                    late_ack_received_at=fixed_now,
                    late_ack_json={"status": "applied"},
                )
            )
            for name, args in [
                ("get_device_status", {"device_id": "CHG-001"}),
                ("get_device_status", {"device_id": "CHG-002"}),
                ("get_fleet_overview", {"window_minutes": 30}),
            ]:
                session.add(
                    ToolCall(
                        tool_call_id=str(uuid4()),
                        provider_call_id=str(uuid4()),
                        run_id=run_id,
                        tool_name=name,
                        args_json=args,
                        status="succeeded",
                        started_at=observed,
                        duration_ms=1.5,
                        result_json={"ok": True, "data": {}},
                    )
                )

        async def snapshot():
            tables = (
                AgentRun,
                AlarmEvent,
                ChargingSession,
                DeviceCommand,
                OperationRequest,
                ScenarioCommandRow,
                SessionReport,
                ToolCall,
                WorkOrder,
                WorkOrderEvent,
            )
            async with app.state.db.sessions() as session:
                return {
                    model.__tablename__: [
                        tuple(row)
                        for row in (
                            await session.execute(
                                select(*model.__table__.columns).order_by(
                                    *model.__table__.primary_key.columns
                                )
                            )
                        ).all()
                    ]
                    for model in tables
                }

        before = await snapshot()
        timeline = await TimelineService(app.state.db).query(
            "CHG-001", observed - timedelta(seconds=1), fixed_now
        )
        assert timeline["event_count"] == 12
        assert timeline["counts_by_source"]["tool_call"] == 2
        assert timeline["counts_by_source"]["session_report"] == 1
        keys = [
            (row["observed_at"], row["source_type"], row["source_id"]) for row in timeline["items"]
        ]
        assert keys == sorted(keys)
        alarm = next(row for row in timeline["items"] if row["source_type"] == "alarm_event")
        assert alarm["detail"]["evidence"] == {"sample": "actual"}
        ack = next(row for row in timeline["items"] if row["source_type"] == "device_ack")
        assert ack["detail"]["ack"] == {"status": "applied"}
        assert (
            ack["observed_at"] == observed
            and ack["received_at"] == fixed_now
            and ack["late_received"]
        )
        async with app.state.db.sessions() as session:
            assert (await session.scalars(select(DeviceCommand))).one().generation == 1
        assert await snapshot() == before
