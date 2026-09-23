import asyncio
import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import ChargingSession, SessionReport
from tests.support.clock import FixedClock
from tests.support.mqtt import MQTTProbe
from tests.support.resources import broker


async def test_real_broker_report_commit_ack_duplicate_conflict_and_no_live_refresh(
    tmp_path, fixed_now
):
    with broker() as (port, prefix):
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                mqtt_port=port,
                mqtt_topic_prefix=prefix,
                database_url=f"sqlite+aiosqlite:///{tmp_path}/reports.db",
            ),
            clock=FixedClock(fixed_now),
        )
        probe = MQTTProbe(port, prefix)
        session_id = str(uuid4())
        report = dict(
            report_id=str(uuid4()),
            device_id="CHG-001",
            session_id=session_id,
            report_seq=1,
            started_at=(fixed_now - timedelta(seconds=600)).isoformat(),
            observed_at=fixed_now.isoformat(),
            ended_at=fixed_now.isoformat(),
            status="COMPLETED",
            start_meter_wh=10000,
            end_meter_wh=13333,
            energy_wh=3333,
            end_reason="USER_STOP",
            meter_quality="exact",
        )
        async with app.router.lifespan_context(app):
            await probe.start()
            try:
                async with app.state.db.sessions.begin() as session:
                    session.add(
                        ChargingSession(
                            session_id=session_id,
                            device_id="CHG-001",
                            status="ACTIVE",
                            requested_power_w=20000,
                        )
                    )
                async with asyncio.timeout(6):
                    while not app.state.mqtt.subscribed:
                        await asyncio.sleep(0.02)

                async def send(value):
                    probe.messages.clear()
                    probe.client.publish(
                        f"{prefix}/devices/CHG-001/session/report", json.dumps(value), qos=1
                    )
                    return await probe.wait_for(
                        lambda topic, payload: topic.endswith("/session/ack")
                    )

                assert (await send(report))["status"] == "stored"
                async with app.state.db.sessions() as session:
                    stored = await session.get(ChargingSession, session_id)
                    assert (stored.status, stored.energy_wh) == ("COMPLETED", 3333)
                    assert (
                        await session.scalar(select(func.count()).select_from(SessionReport)) == 1
                    )
                assert (await send(report))["status"] == "stored"
                assert (await send({**report, "end_meter_wh": 13334, "energy_wh": 3334}))[
                    "status"
                ] == "conflict"
                assert (
                    await send({**report, "report_id": str(uuid4()), "session_id": str(uuid4())})
                )["status"] == "rejected"
                assert (
                    await send(
                        {
                            **report,
                            "report_id": str(uuid4()),
                            "report_seq": 2,
                            "status": "ACTIVE",
                            "ended_at": None,
                            "end_reason": None,
                        }
                    )
                )["status"] == "stored"
                async with app.state.db.sessions() as session:
                    assert (await session.get(ChargingSession, session_id)).status == "COMPLETED"
                assert (await app.state.store.device_status("CHG-001"))[
                    "connection_state"
                ] == "unknown"
            finally:
                await probe.close()


async def test_operations_simulator_real_mqtt_control_and_reports(tmp_path):
    from backend.app.clocks import DataClock
    from simulator.main import DeviceClient

    clock = DataClock()
    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=port,
            mqtt_topic_prefix=prefix,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/ops.db",
            simulator_mode="operations",
            simulator_state_dir=str(tmp_path / "sim"),
        )
        app = create_app(settings)
        probe = MQTTProbe(port, prefix)
        device = DeviceClient("CHG-001", settings)
        async with app.router.lifespan_context(app):
            await probe.start()
            await device.start()
            try:
                initial = await probe.wait_for(
                    lambda t, p: t.endswith("/telemetry") and p.get("schema_version") == 2
                )
                assert initial["session_state"] == "IDLE" and initial["power_kw"] == 0
                session_id = str(uuid4())
                async with app.state.db.sessions.begin() as session:
                    session.add(
                        ChargingSession(
                            session_id=session_id,
                            device_id="CHG-001",
                            status="ACTIVE",
                            requested_power_w=20000,
                        )
                    )

                async def control(generation, action, args):
                    now = clock.now()
                    command = dict(
                        command_id=str(uuid4()),
                        device_id="CHG-001",
                        generation=generation,
                        action=action,
                        args=args,
                        issued_at=now.isoformat(),
                        expires_at=(now + timedelta(seconds=5)).isoformat(),
                    )
                    probe.client.publish(
                        f"{prefix}/devices/CHG-001/control/set", json.dumps(command), qos=1
                    )
                    return await probe.wait_for(
                        lambda t, p: (
                            t.endswith("/control/ack")
                            and p.get("command_id") == command["command_id"]
                        )
                    )

                assert (
                    await control(
                        1, "start_session", {"session_id": session_id, "requested_power_w": 20000}
                    )
                )["status"] == "applied"
                ack = await probe.wait_for(
                    lambda t, p: t.endswith("/session/ack") and p.get("session_id") == session_id
                )
                assert ack["status"] == "stored"
                assert (await control(2, "set_power_limit", {"power_limit_w": 20000}))[
                    "status"
                ] == "applied"
                sample = await probe.wait_for(
                    lambda t, p: (
                        t.endswith("/telemetry") and p.get("applied_control_generation") == 2
                    )
                )
                assert sample["power_kw"] == 20 and sample["session_id"] == session_id
                scenario_id = str(uuid4())
                probe.client.publish(
                    f"{prefix}/devices/CHG-001/scenario/set",
                    json.dumps(
                        dict(command_id=scenario_id, device_id="CHG-001", scenario="offline")
                    ),
                    qos=1,
                )
                await probe.wait_for(
                    lambda t, p: t.endswith("/scenario/ack") and p.get("command_id") == scenario_id
                )
                await asyncio.sleep(16)
                assert (await app.state.store.device_status("CHG-001"))[
                    "connection_state"
                ] == "offline"
                assert any(
                    t.endswith("/session/report") and p.get("report_seq", 0) > 1
                    for t, p in probe.messages
                )

                assert (await control(3, "stop_session", {"session_id": session_id}))[
                    "status"
                ] == "applied"
                await probe.wait_for(
                    lambda t, p: t.endswith("/session/report") and p.get("status") == "COMPLETED"
                )
                async with asyncio.timeout(6):
                    while True:
                        async with app.state.db.sessions() as session:
                            stored = await session.get(ChargingSession, session_id)
                            if stored.status == "COMPLETED":
                                assert stored.energy_wh > 0
                                break
                        await asyncio.sleep(0.02)
            finally:
                await device.close()
                await probe.close()


async def test_v2_ingestion_duplicates_conflicts_and_retained_do_not_refresh(
    tmp_path, fixed_now, valid_payload
):
    from backend.app.db import Database
    from backend.app.models import Telemetry
    from backend.app.telemetry.ingest import TelemetryStore
    from tests.unit.test_telemetry_v2 import payload_v2

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/v2.db",
    )
    db = Database(settings)
    clock = FixedClock(fixed_now)
    await db.initialize(clock)
    store = TelemetryStore(db, settings, clock)
    raw = payload_v2(valid_payload)
    topic = "charge/v1/devices/CHG-002/telemetry"
    try:
        assert await store.receive(json.dumps(raw).encode(), topic, fixed_now, False) == "accepted"
        assert (
            await store.receive(
                json.dumps(raw).encode(), topic, fixed_now + timedelta(seconds=16), False
            )
            == "duplicate"
        )
        assert (
            await store.receive(
                json.dumps({**raw, "meter_total_wh": 15001}).encode(), topic, fixed_now, False
            )
            == "conflict"
        )
        replay = {
            **raw,
            "message_id": str(uuid4()),
            "seq": 18,
            "ts": (fixed_now - timedelta(seconds=1)).isoformat(),
        }
        assert (
            await store.receive(json.dumps(replay).encode(), topic, fixed_now, False) == "accepted"
        )
        retained = {
            **raw,
            "message_id": str(uuid4()),
            "seq": 19,
            "ts": (fixed_now + timedelta(seconds=16)).isoformat(),
        }
        assert (
            await store.receive(
                json.dumps(retained).encode(), topic, fixed_now + timedelta(seconds=16), True
            )
            == "rejected"
        )
        clock.advance(16)
        status = await store.device_status("CHG-002")
        assert status["connection_state"] == "offline"
        assert status["session_id"] == raw["session_id"]
        assert status["meter_total_wh"] == 15000
        assert status["message_id"] == raw["message_id"]
        async with db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Telemetry)) == 2
    finally:
        await db.close()


async def test_simulator_process_kill_preserves_published_meter(tmp_path):
    import sys

    from backend.app.clocks import DataClock

    code = """
import asyncio,sys
from backend.app.config import Settings
from simulator.main import DeviceClient
async def main():
    settings=Settings(_env_file=None,app_env="test",mqtt_port=int(sys.argv[1]),mqtt_topic_prefix=sys.argv[2],simulator_mode="operations",simulator_state_dir=sys.argv[3])
    device=DeviceClient("CHG-001",settings)
    await device.start()
    try:
        await asyncio.Event().wait()
    finally:
        await device.close()
asyncio.run(main())
"""
    clock = DataClock()
    with broker() as (port, prefix):
        probe = MQTTProbe(port, prefix)
        await probe.start()
        child = None
        try:

            async def launch():
                return await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-c",
                    code,
                    str(port),
                    prefix,
                    str(tmp_path / "state"),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )

            child = await launch()
            await probe.wait_for(lambda t, p: t.endswith("/telemetry"))
            session_id = str(uuid4())
            for generation, action, args in [
                (1, "start_session", {"session_id": session_id, "requested_power_w": 20000}),
                (2, "set_power_limit", {"power_limit_w": 20000}),
            ]:
                now = clock.now()
                command = dict(
                    command_id=str(uuid4()),
                    device_id="CHG-001",
                    generation=generation,
                    action=action,
                    args=args,
                    issued_at=now.isoformat(),
                    expires_at=(now + timedelta(seconds=5)).isoformat(),
                )
                probe.client.publish(
                    f"{prefix}/devices/CHG-001/control/set", json.dumps(command), qos=1
                )
                ack = await probe.wait_for(
                    lambda t, p: t.endswith("/control/ack") and p.get("generation") == generation
                )
                assert ack["status"] == "applied"
            published = await probe.wait_for(
                lambda t, p: t.endswith("/telemetry") and p.get("meter_total_wh", 0) > 0
            )
            child.kill()
            await child.wait()
            probe.messages.clear()
            child = await launch()
            report = await probe.wait_for(
                lambda t, p: t.endswith("/session/report") and p.get("status") == "INTERRUPTED"
            )
            assert report["end_reason"] == "SIMULATOR_RESTART"
            assert report["meter_quality"] == "checkpoint"
            assert report["end_meter_wh"] >= published["meter_total_wh"]
            fresh = await probe.wait_for(lambda t, p: t.endswith("/telemetry"))
            assert fresh["session_state"] == "IDLE" and fresh["power_kw"] == 0
            assert fresh["meter_total_wh"] == report["end_meter_wh"]
        finally:
            if child and child.returncode is None:
                child.kill()
                await child.wait()
            await probe.close()
