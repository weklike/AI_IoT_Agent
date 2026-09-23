import asyncio
import json
from datetime import timedelta
from uuid import uuid4

import pytest

from backend.app.charging.contracts import ControlAck
from backend.app.charging.control import ChargingControl
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.telemetry.ingest import TelemetryStore
from tests.support.clock import FixedClock


async def test_mismatched_acks_do_not_apply_and_only_matching_fresh_effect_verifies(
    tmp_path, fixed_now, valid_payload
):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/ack.db",
    )
    clock = FixedClock(fixed_now)
    db = Database(settings)
    await db.initialize(clock)
    store = TelemetryStore(db, settings, clock)

    class Publisher:
        connected = True

        def publish(self, *args):
            return True

    control = ChargingControl(db, settings, clock, Publisher())
    topic = "charge/v1/devices/CHG-001/control/ack"
    idle = {
        **valid_payload,
        "device_id": "CHG-001",
        "schema_version": 2,
        "session_id": None,
        "session_state": "IDLE",
        "requested_power_w": 0,
        "power_limit_w": 0,
        "meter_total_wh": 0,
        "session_energy_wh": None,
        "applied_control_generation": 0,
        "power_kw": 0,
        "current_a": 0,
        "operating_state": "idle",
    }
    try:
        await store.receive(
            json.dumps(idle).encode(), topic.replace("control/ack", "telemetry"), fixed_now, False
        )
        created = await control.create(
            "CHG-001", str(uuid4()), "start_session", {"requested_power_w": 20000}
        )
        row = await control.get(created["command_id"])
        ack = dict(
            command_id=created["command_id"],
            device_id="CHG-001",
            generation=1,
            action="start_session",
            args=row["args_json"],
            issued_at=fixed_now,
            expires_at=fixed_now + timedelta(seconds=5),
            applied_at=fixed_now,
            status="applied",
            error_code=None,
            actual_state={},
        )
        invalid = [
            ({"device_id": "CHG-002"}, topic.replace("001", "002")),
            ({"generation": 2}, topic),
            ({"action": "stop_session", "args": {"session_id": created["session_id"]}}, topic),
            ({}, topic.replace("001", "002")),
        ]
        for changes, incoming_topic in invalid:
            await control.ack(ControlAck.model_validate({**ack, **changes}), incoming_topic)
            unchanged = await control.get(created["command_id"])
            assert unchanged["status"] == "pending" and unchanged["ack_json"] is None
        with pytest.raises(DomainError) as error:
            await control.create(
                "CHG-001", str(uuid4()), "stop_session", {"session_id": created["session_id"]}
            )
        assert error.value.code == "CONTROL_BUSY"
        await control.ack(ControlAck.model_validate(ack), topic)
        await asyncio.sleep(0.15)
        assert (await control.get(created["command_id"]))["verification_status"] == "pending"
        clock.advance(1)
        active = {
            **idle,
            "message_id": str(uuid4()),
            "seq": idle["seq"] + 1,
            "ts": clock.now().isoformat(),
            "session_state": "ACTIVE",
            "session_id": str(uuid4()),
            "requested_power_w": 20000,
            "session_energy_wh": 0,
            "applied_control_generation": 1,
        }
        assert (
            await store.receive(
                json.dumps(active).encode(),
                topic.replace("control/ack", "telemetry"),
                clock.now(),
                False,
            )
            == "accepted"
        )
        await asyncio.sleep(0.15)
        assert (await control.get(created["command_id"]))["verification_status"] == "pending"
        clock.advance(1)
        active.update(
            message_id=str(uuid4()),
            seq=active["seq"] + 1,
            ts=clock.now().isoformat(),
            session_id=created["session_id"],
            applied_control_generation=2,
        )
        assert (
            await store.receive(
                json.dumps(active).encode(),
                topic.replace("control/ack", "telemetry"),
                clock.now(),
                False,
            )
            == "accepted"
        )
        await asyncio.sleep(0.15)
        assert (await control.get(created["command_id"]))["verification_status"] == "pending"
        clock.advance(1)
        active.update(
            message_id=str(uuid4()),
            seq=active["seq"] + 1,
            ts=clock.now().isoformat(),
            applied_control_generation=1,
        )
        assert (
            await store.receive(
                json.dumps(active).encode(),
                topic.replace("control/ack", "telemetry"),
                clock.now(),
                False,
            )
            == "accepted"
        )
        async with asyncio.timeout(2):
            while (await control.get(created["command_id"]))["verification_status"] == "pending":
                await asyncio.sleep(0.02)
        assert (await control.get(created["command_id"]))["verification_status"] == "verified"
    finally:
        await control.close()
        await db.close()
