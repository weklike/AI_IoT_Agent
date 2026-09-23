import asyncio
from uuid import uuid4

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from simulator.main import DeviceClient
from tests.support.resources import broker


async def test_http_start_stop_idempotency_and_verified_feedback(tmp_path):
    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=port,
            mqtt_topic_prefix=prefix,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/control.db",
            simulator_mode="operations",
            simulator_state_dir=str(tmp_path / "state"),
        )
        app = create_app(settings)
        device = DeviceClient("CHG-001", settings)
        async with app.router.lifespan_context(app):
            await device.start()
            try:
                async with asyncio.timeout(8):
                    while not (await app.state.store.device_status("CHG-001"))["data_fresh"]:
                        await asyncio.sleep(0.02)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    body = dict(request_id=str(uuid4()), requested_power_w=20000)
                    start = await client.post("/api/devices/CHG-001/charging/start", json=body)
                    assert start.status_code == 202, start.text
                    data = start.json()["data"]
                    assert (
                        await client.post("/api/devices/CHG-001/charging/start", json=body)
                    ).json()["data"] == data
                    assert (
                        await client.post(
                            "/api/devices/CHG-001/charging/start",
                            json={**body, "requested_power_w": 10000},
                        )
                    ).status_code == 409

                    async def terminal(command_id):
                        async with asyncio.timeout(10):
                            while True:
                                response = await client.get("/api/device-commands/" + command_id)
                                assert response.status_code == 200, response.text
                                row = response.json()["data"]
                                if row["verification_status"] != "pending":
                                    return row
                                await asyncio.sleep(0.05)

                    result = await terminal(data["command_id"])
                    assert result["status"] == "applied"
                    assert result["verification_status"] == "verified"
                    assert device.charging.power_limit_w == 0
                    stop = await client.post(
                        "/api/devices/CHG-001/charging/stop",
                        json=dict(request_id=str(uuid4()), session_id=data["session_id"]),
                    )
                    assert stop.status_code == 202, stop.text
                    result = await terminal(stop.json()["data"]["command_id"])
                    assert result["verification_status"] == "verified"
            finally:
                await device.close()


async def test_no_ack_times_out_and_duplicate_request_reuses_original(
    tmp_path, fixed_now, valid_payload
):
    import json
    import time

    from tests.support.clock import FixedClock
    from tests.support.mqtt import MQTTProbe

    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=port,
            mqtt_topic_prefix=prefix,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/timeout.db",
        )
        app = create_app(settings, clock=FixedClock(fixed_now))
        probe = MQTTProbe(port, prefix)
        async with app.router.lifespan_context(app):
            await probe.start()
            try:
                async with asyncio.timeout(6):
                    while not app.state.mqtt.subscribed:
                        await asyncio.sleep(0.02)
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
                assert (
                    await app.state.store.receive(
                        json.dumps(idle).encode(),
                        f"{prefix}/devices/CHG-001/telemetry",
                        fixed_now,
                        False,
                    )
                    == "accepted"
                )
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    body = dict(request_id=str(uuid4()), requested_power_w=20000)
                    began = time.monotonic()
                    response = await client.post("/api/devices/CHG-001/charging/start", json=body)
                    assert response.status_code == 202, response.text
                    data = response.json()["data"]
                    other = await client.post(
                        "/api/devices/CHG-001/charging/start",
                        json={**body, "request_id": str(uuid4())},
                    )
                    assert other.status_code == 409
                    assert other.json()["error"]["code"] == "CONTROL_BUSY"
                    async with asyncio.timeout(6):
                        while True:
                            row = (
                                await client.get("/api/device-commands/" + data["command_id"])
                            ).json()["data"]
                            if row["status"] != "pending":
                                break
                            await asyncio.sleep(0.02)
                    assert (
                        row["status"] == "timed_out" and row["verification_status"] == "unconfirmed"
                    )
                    assert 5 <= time.monotonic() - began <= 5.5
                    retry = await client.post("/api/devices/CHG-001/charging/start", json=body)
                    assert retry.json()["data"] == data
                    commands = [p for t, p in probe.messages if t.endswith("/control/set")]
                    assert len(commands) == 1
                    command = commands[0]
                    late = {
                        **command,
                        "applied_at": fixed_now.isoformat(),
                        "status": "applied",
                        "error_code": None,
                        "actual_state": {},
                    }
                    probe.client.publish(
                        f"{prefix}/devices/CHG-001/control/ack", json.dumps(late), qos=1
                    )
                    async with asyncio.timeout(3):
                        while True:
                            row = (
                                await client.get("/api/device-commands/" + data["command_id"])
                            ).json()["data"]
                            if row["late_ack_json"]:
                                break
                            await asyncio.sleep(0.02)
                    assert row["status"] == "timed_out"
            finally:
                await probe.close()


async def test_commit_before_publish_restart_preserves_request_without_replay(
    tmp_path, fixed_now, valid_payload
):
    import json

    import pytest

    from backend.app.charging.control import ChargingControl
    from backend.app.db import Database
    from backend.app.telemetry.ingest import TelemetryStore
    from tests.support.clock import FixedClock

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/crash.db",
    )
    db = Database(settings)
    clock = FixedClock(fixed_now)
    await db.initialize(clock)
    store = TelemetryStore(db, settings, clock)
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
    await store.receive(
        json.dumps(idle).encode(), "charge/v1/devices/CHG-001/telemetry", fixed_now, False
    )

    class CrashPublisher:
        connected = True
        calls = 0

        def publish(self, *args):
            self.calls += 1
            raise RuntimeError("process lost after commit")

    publisher = CrashPublisher()
    control = ChargingControl(db, settings, clock, publisher)
    request_id = str(uuid4())
    try:
        with pytest.raises(RuntimeError, match="process lost"):
            await control.create(
                "CHG-001", request_id, "start_session", {"requested_power_w": 20000}
            )
        await db.initialize(clock)
        result = await control.create(
            "CHG-001", request_id, "start_session", {"requested_power_w": 20000}
        )
        assert publisher.calls == 1
        row = await control.get(result["command_id"])
        assert row["status"] == "interrupted" and row["verification_status"] == "unconfirmed"
    finally:
        await control.close()
        await db.close()


async def test_slow_effect_query_cannot_verify_after_four_second_deadline(
    tmp_path, fixed_now, valid_payload, monkeypatch
):
    import json
    import time
    from datetime import timedelta

    from backend.app.charging.contracts import ControlAck
    from backend.app.charging.control import ChargingControl
    from backend.app.db import Database
    from backend.app.telemetry.ingest import TelemetryStore
    from tests.support.clock import FixedClock

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/verify.db",
    )
    db = Database(settings)
    clock = FixedClock(fixed_now)
    await db.initialize(clock)
    store = TelemetryStore(db, settings, clock)
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
    await store.receive(
        json.dumps(idle).encode(), "charge/v1/devices/CHG-001/telemetry", fixed_now, False
    )

    class Publisher:
        connected = True

        def publish(self, *args):
            return True

    control = ChargingControl(db, settings, clock, Publisher())
    try:
        result = await control.create(
            "CHG-001", str(uuid4()), "start_session", {"requested_power_w": 20000}
        )
        row = await control.get(result["command_id"])

        async def slow(*args):
            await asyncio.sleep(4.2)
            return {
                "data_fresh": True,
                "applied_control_generation": 1,
                "session_id": result["session_id"],
                "session_state": "ACTIVE",
                "power_limit_w": 0,
                "requested_power_w": 20000,
                "message_id": "new",
                "sample_ts": fixed_now,
            }

        monkeypatch.setattr("backend.app.charging.control.device_status", slow)
        began = time.monotonic()
        await control.ack(
            ControlAck(
                command_id=result["command_id"],
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
            ),
            "charge/v1/devices/CHG-001/control/ack",
        )
        async with asyncio.timeout(5):
            while result["command_id"] in control.tasks:
                await asyncio.sleep(0.02)
        final = await control.get(result["command_id"])
        assert final["status"] == "applied"
        assert final["verification_status"] == "unconfirmed"
        assert time.monotonic() - began <= 4.5
    finally:
        await control.close()
        await db.close()


async def test_concurrent_start_serializes_per_device_and_rejects_invalid_inputs(
    tmp_path, fixed_now, valid_payload
):
    import json

    from backend.app.charging.control import ChargingControl
    from backend.app.db import Database
    from backend.app.errors import DomainError
    from backend.app.telemetry.ingest import TelemetryStore
    from tests.support.clock import FixedClock

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/concurrent.db",
    )
    db = Database(settings)
    clock = FixedClock(fixed_now)
    await db.initialize(clock)
    store = TelemetryStore(db, settings, clock)

    class Publisher:
        connected = True
        calls = []

        def publish(self, topic, payload):
            self.calls.append((topic, payload))
            return True

    control = ChargingControl(db, settings, clock, Publisher())
    try:
        for device_id in ("CHG-001", "CHG-002"):
            idle = {
                **valid_payload,
                "message_id": str(uuid4()),
                "device_id": device_id,
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
            assert (
                await store.receive(
                    json.dumps(idle).encode(),
                    f"charge/v1/devices/{device_id}/telemetry",
                    fixed_now,
                    False,
                )
                == "accepted"
            )
        results = await asyncio.gather(
            *(
                control.create(device, str(uuid4()), "start_session", {"requested_power_w": 20000})
                for device in ("CHG-001", "CHG-001", "CHG-002")
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(item, dict) for item in results) == 2
        errors = [item for item in results if isinstance(item, DomainError)]
        assert len(errors) == 1 and errors[0].code == "CONTROL_BUSY"
        assert len(control.mqtt.calls) == 2
    finally:
        await control.close()
        assert not control.tasks
        await db.close()


async def test_http_strict_control_arguments_and_unknown_records(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/invalid.db",
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for power in (True, "1000", 0, 101, 20100, float("inf")):
                # JSON cannot contain Infinity; use literal bytes to exercise the decoder boundary.
                import json

                response = await client.post(
                    "/api/devices/CHG-001/charging/start",
                    content=json.dumps({"request_id": str(uuid4()), "requested_power_w": power}),
                    headers={"content-type": "application/json"},
                )
                assert response.status_code == 422, response.text
            response = await client.post(
                "/api/devices/CHG-999/charging/start",
                json={"request_id": str(uuid4()), "requested_power_w": 1000},
            )
            assert response.status_code == 404
            assert (await client.get("/api/device-commands/" + str(uuid4()))).status_code == 404
            assert (await client.get("/api/charging-sessions/" + str(uuid4()))).status_code == 404
