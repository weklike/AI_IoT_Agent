import asyncio
from uuid import UUID, uuid4

import pytest

from backend.app.config import Settings
from backend.app.contracts import ScenarioAck
from backend.app.db import Database
from backend.app.simulator_control import ScenarioControl
from tests.support.clock import FixedClock


class Publisher:
    connected = True
    messages = []

    def publish(self, topic, payload):
        self.messages.append((topic, payload))
        return self.connected


@pytest.fixture
async def control(tmp_path, fixed_now):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        scenario_ack_timeout_seconds=0.05,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
    )
    db = Database(settings)
    clock = FixedClock(fixed_now)
    await db.initialize(clock)
    controller = ScenarioControl(db, settings, clock, Publisher())
    yield controller
    await controller.close()
    await db.close()


async def test_pending_matching_ack(control, fixed_now):
    command = await control.create("CHG-002", "overheat")
    assert command["status"] == "pending"
    ack = ScenarioAck(
        command_id=command["command_id"],
        device_id="CHG-002",
        scenario="overheat",
        status="applied",
        applied_at=fixed_now,
    )
    await control.ack(ack, f"{control.settings.mqtt_topic_prefix}/devices/CHG-002/scenario/ack")
    assert (await control.get(command["command_id"]))["status"] == "applied"


async def test_timeout_uses_monotonic_and_late_ack(control, fixed_now):
    command = await control.create("CHG-002", "offline")
    ack = ScenarioAck(
        command_id=uuid4(),
        device_id="CHG-002",
        scenario="offline",
        status="applied",
        applied_at=fixed_now,
    )
    await control.ack(ack, f"{control.settings.mqtt_topic_prefix}/devices/CHG-002/scenario/ack")
    assert (await control.get(command["command_id"]))["status"] == "pending"
    await asyncio.sleep(0.08)  # Fixed DataClock deliberately never advances.
    assert (await control.get(command["command_id"]))["status"] == "timed_out"
    ack.command_id = UUID(command["command_id"])
    await control.ack(ack, f"{control.settings.mqtt_topic_prefix}/devices/CHG-002/scenario/ack")
    result = await control.get(command["command_id"])
    assert result["status"] == "timed_out"
    assert result["late_ack_json"]["status"] == "applied"


async def test_mismatched_ack_and_broker_unavailable(control, fixed_now):
    from backend.app.errors import DomainError

    command = await control.create("CHG-002", "overheat")
    ack = ScenarioAck(
        command_id=command["command_id"],
        device_id="CHG-001",
        scenario="overheat",
        status="applied",
        applied_at=fixed_now,
    )
    await control.ack(ack, f"{control.settings.mqtt_topic_prefix}/devices/CHG-001/scenario/ack")
    assert (await control.get(command["command_id"]))["status"] == "pending"
    control.publisher.connected = False
    with pytest.raises(DomainError) as error:
        await control.create("CHG-002", "normal")
    assert error.value.status == 503


async def test_real_api_scenarios_and_offline_recovery(tmp_path):
    import httpx

    from backend.app.main import create_app
    from simulator.main import DeviceClient
    from tests.support.resources import broker

    with broker() as (port, prefix):
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                mqtt_port=port,
                mqtt_topic_prefix=prefix,
                database_url=f"sqlite+aiosqlite:///{tmp_path}/real.db",
            )
        )
        async with app.router.lifespan_context(app):
            device = DeviceClient("CHG-002", app.state.settings)
            await device.start()
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:

                    async def status():
                        return (await client.get("/api/devices/CHG-002")).json()["data"]

                    async def scenario(value):
                        response = await client.post(
                            "/api/simulator/scenarios",
                            json={"device_id": "CHG-002", "scenario": value},
                        )
                        assert response.status_code == 202
                        assert response.json()["data"]["status"] == "pending"
                        key = response.json()["data"]["command_id"]
                        async with asyncio.timeout(5):
                            while (await client.get("/api/simulator/commands/" + key)).json()[
                                "data"
                            ]["status"] == "pending":
                                await asyncio.sleep(0.02)
                        assert (await client.get("/api/simulator/commands/" + key)).json()["data"][
                            "status"
                        ] == "applied"

                    async with asyncio.timeout(8):
                        while (await status())["connection_state"] != "online":
                            await asyncio.sleep(0.02)
                    await scenario("overheat")
                    async with asyncio.timeout(4):
                        while (await status())["health_state"] != "overheat":
                            await asyncio.sleep(0.02)
                    await scenario("offline")
                    assert (await status())["connection_state"] == "online"
                    async with asyncio.timeout(18):
                        while (await status())["connection_state"] != "offline":
                            await asyncio.sleep(0.1)
                    await scenario("normal")
                    async with asyncio.timeout(4):
                        while (await status())["connection_state"] != "online":
                            await asyncio.sleep(0.02)
                    assert (await status())["health_state"] == "normal"
            finally:
                await device.close()
