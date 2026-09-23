import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DeviceCommand
from simulator.main import DeviceClient
from tests.support.mqtt import MQTTProbe
from tests.support.resources import broker


async def test_real_three_device_plan_preview_and_decrease_before_increase(tmp_path):
    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=port,
            mqtt_topic_prefix=prefix,
            simulator_mode="operations",
            simulator_state_dir=str(tmp_path / "state"),
            database_url=f"sqlite+aiosqlite:///{tmp_path}/power.db",
        )
        app = create_app(settings)
        devices = [DeviceClient(device, settings) for device in ("CHG-001", "CHG-002", "CHG-003")]
        probe = MQTTProbe(port, prefix)
        async with app.router.lifespan_context(app):
            await probe.start()
            for device in devices:
                await device.start()
            try:
                async with asyncio.timeout(8):
                    while not all(
                        [
                            (await app.state.store.device_status(device.device.device_id))[
                                "data_fresh"
                            ]
                            for device in devices
                        ]
                    ):
                        await asyncio.sleep(0.02)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:

                    async def wait(path, field, done, timeout=15):
                        async with asyncio.timeout(timeout):
                            while True:
                                response = await client.get(path)
                                assert response.status_code == 200, response.text
                                data = response.json()["data"]
                                if data[field] in done:
                                    return data
                                await asyncio.sleep(0.05)

                    starts = await asyncio.gather(
                        *(
                            client.post(
                                f"/api/devices/{device.device.device_id}/charging/start",
                                json={"request_id": str(uuid4()), "requested_power_w": 20000},
                            )
                            for device in devices
                        )
                    )
                    for response in starts:
                        assert response.status_code == 202, response.text
                        assert (
                            await wait(
                                "/api/device-commands/" + response.json()["data"]["command_id"],
                                "verification_status",
                                {"verified", "unconfirmed"},
                            )
                        )["verification_status"] == "verified"

                    async def make_plan(strategy, priority=None):
                        async with app.state.db.sessions() as session:
                            before = await session.scalar(
                                select(func.count()).select_from(DeviceCommand)
                            )
                        body = {
                            "request_id": str(uuid4()),
                            "budget_w": 45000,
                            "strategy": strategy,
                            "device_priority": priority,
                        }
                        response = await client.post("/api/power-plans", json=body)
                        assert response.status_code == 201, response.text
                        plan = response.json()["data"]
                        async with app.state.db.sessions() as session:
                            assert (
                                await session.scalar(
                                    select(func.count()).select_from(DeviceCommand)
                                )
                                == before
                            )
                        execute = {"request_id": str(uuid4())}
                        response = await client.post(
                            f"/api/power-plans/{plan['plan_id']}/execute", json=execute
                        )
                        assert response.status_code == 202, response.text
                        assert (
                            await client.post(
                                f"/api/power-plans/{plan['plan_id']}/execute", json=execute
                            )
                        ).json()["data"] == response.json()["data"]
                        return await wait(
                            "/api/power-plans/" + plan["plan_id"],
                            "status",
                            {"VERIFIED", "PARTIAL", "REJECTED", "INTERRUPTED"},
                        )

                    equal = await make_plan("equal")
                    assert equal["status"] == "VERIFIED", equal
                    assert all(device.charging.power_limit_w == 15000 for device in devices)
                    probe.messages.clear()
                    priority = await make_plan("priority", ["CHG-002", "CHG-001", "CHG-003"])
                    assert priority["status"] == "VERIFIED", priority
                    assert [device.charging.power_limit_w for device in devices] == [
                        20000,
                        20000,
                        5000,
                    ]
                    command_messages = [
                        (t, p) for t, p in probe.messages if t.endswith("/control/set")
                    ]
                    assert command_messages[0][1]["device_id"] == "CHG-003"
                    assert command_messages[0][1]["args"]["power_limit_w"] == 5000
                    decrease_generation = command_messages[0][1]["generation"]
                    first_increase = next(
                        i
                        for i, (t, p) in enumerate(probe.messages)
                        if t.endswith("/control/set") and p["args"]["power_limit_w"] == 20000
                    )
                    assert any(
                        t.endswith("/CHG-003/telemetry")
                        and p.get("applied_control_generation") == decrease_generation
                        for t, p in probe.messages[:first_increase]
                    )
                    station = (await client.get("/api/station-state")).json()["data"]
                    assert station["budget_w"] == 45000 and station["executing_plan_id"] is None
                    original_apply = devices[0]._apply

                    def drop_limit(topic, payload):
                        import json

                        if (
                            topic.endswith("/control/set")
                            and json.loads(payload).get("action") == "set_power_limit"
                        ):
                            return
                        original_apply(topic, payload)

                    devices[0]._apply = drop_limit
                    probe.messages.clear()
                    partial = await make_plan("equal")
                    assert partial["status"] == "PARTIAL"
                    assert partial["commands"]["CHG-001"]["status"] == "timed_out"
                    assert not any(t.endswith("/CHG-003/control/set") for t, p in probe.messages)
                    assert devices[1].charging.power_limit_w == 15000
                    assert devices[2].charging.power_limit_w == 5000

            finally:
                for device in devices:
                    await device.close()
                await probe.close()


async def test_preview_control_fingerprint_and_expiry(tmp_path, fixed_now, valid_payload):
    import json

    from backend.app.models import ChargingSession
    from tests.support.clock import FixedClock

    clock = FixedClock(fixed_now)
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/preview.db",
    )
    app = create_app(settings, clock=clock)
    samples = {}
    async with app.router.lifespan_context(app):
        async with app.state.db.sessions.begin() as session:
            for device in ("CHG-001", "CHG-002", "CHG-003"):
                identity = str(uuid4())
                session.add(
                    ChargingSession(
                        session_id=identity,
                        device_id=device,
                        status="ACTIVE",
                        requested_power_w=20000,
                    )
                )
                samples[device] = {
                    **valid_payload,
                    "device_id": device,
                    "message_id": str(uuid4()),
                    "schema_version": 2,
                    "session_id": identity,
                    "session_state": "ACTIVE",
                    "requested_power_w": 20000,
                    "power_limit_w": 0,
                    "meter_total_wh": 0,
                    "session_energy_wh": 0,
                    "applied_control_generation": 0,
                    "current_a": 0,
                    "power_kw": 0,
                }

        async def receive(device):
            return await app.state.store.receive(
                json.dumps(samples[device]).encode(),
                f"charge/v1/devices/{device}/telemetry",
                clock.now(),
                False,
            )

        for device in samples:
            assert await receive(device) == "accepted"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def preview(budget=0):
                response = await client.post(
                    "/api/power-plans",
                    json={"request_id": str(uuid4()), "budget_w": budget, "strategy": "equal"},
                )
                assert response.status_code == 201, response.text
                return response.json()["data"]["plan_id"]

            plan = await preview()
            clock.advance(2)
            for device in samples:
                samples[device].update(
                    message_id=str(uuid4()), seq=18, ts=clock.now().isoformat(), temperature_c=40
                )
                assert await receive(device) == "accepted"
            accepted = await client.post(
                f"/api/power-plans/{plan}/execute", json={"request_id": str(uuid4())}
            )
            assert accepted.status_code == 202, accepted.text
            async with asyncio.timeout(3):
                while (await client.get("/api/power-plans/" + plan)).json()["data"][
                    "status"
                ] == "EXECUTING":
                    await asyncio.sleep(0.02)
            assert (await client.get("/api/power-plans/" + plan)).json()["data"][
                "status"
            ] == "VERIFIED"
            stale = await preview(45000)
            clock.advance(2)
            samples["CHG-001"].update(
                message_id=str(uuid4()),
                seq=19,
                ts=clock.now().isoformat(),
                power_limit_w=100,
                current_a=0.25,
                power_kw=0.1,
            )
            assert await receive("CHG-001") == "accepted"
            rejected = await client.post(
                f"/api/power-plans/{stale}/execute", json={"request_id": str(uuid4())}
            )
            assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "PLAN_STALE"
            expired = await preview(45000)
            clock.advance(121)
            rejected = await client.post(
                f"/api/power-plans/{expired}/execute", json={"request_id": str(uuid4())}
            )
            assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "PLAN_STALE"


async def test_plan_uses_real_thirty_second_deadline_and_clears_slot(
    tmp_path, fixed_now, monkeypatch
):
    import time

    from backend.app.models import PowerPlan, StationState
    from tests.support.clock import FixedClock

    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/deadline.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        plan_id = str(uuid4())
        async with app.state.db.sessions.begin() as session:
            session.add(
                PowerPlan(
                    plan_id=plan_id,
                    strategy="equal",
                    budget_w=45000,
                    station_revision=1,
                    snapshot_json={
                        "confirmed_budget_w": 60000,
                        "fingerprint": {
                            device: {"power_limit_w": 0}
                            for device in ("CHG-001", "CHG-002", "CHG-003")
                        },
                    },
                    allocation_json=dict.fromkeys(("CHG-001", "CHG-002", "CHG-003"), 15000),
                    results_json={},
                    status="EXECUTING",
                    created_at=fixed_now,
                )
            )
            await session.flush()
            station = await session.get(StationState, 1)
            station.executing_plan_id = plan_id

        async def blocked_phase(*args):
            await asyncio.sleep(31)

        monkeypatch.setattr(app.state.power, "_phase", blocked_phase)
        app.state.power.owned[plan_id] = set()
        began = time.monotonic()
        await app.state.power._run(plan_id)
        elapsed = time.monotonic() - began
        assert 30 <= elapsed <= 35
        row = await app.state.power.get(plan_id)
        assert row["status"] == "PARTIAL" and row["results_json"]["error_code"] == "PLAN_TIMEOUT"
        assert (await app.state.power.station())["executing_plan_id"] is None
