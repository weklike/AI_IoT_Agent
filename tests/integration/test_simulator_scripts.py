import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Device, DeviceCommand, ScenarioCommandRow
from simulator.main import DeviceClient
from tests.support.resources import broker


async def test_two_fixed_sixty_second_scripts_real_broker(tmp_path):
    with broker() as (port, prefix):
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                mqtt_port=port,
                mqtt_topic_prefix=prefix,
                database_url=f"sqlite+aiosqlite:///{tmp_path}/scripts.db",
            )
        )
        async with app.router.lifespan_context(app):
            devices = [
                DeviceClient(identifier, app.state.settings)
                for identifier in ("CHG-001", "CHG-002")
            ]
            for device in devices:
                await device.start()
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    ids = []
                    for identifier, name in [
                        ("CHG-001", "normal_overheat_normal"),
                        ("CHG-002", "normal_offline_normal"),
                    ]:
                        payload = {
                            "request_id": str(uuid4()),
                            "device_id": identifier,
                            "script_name": name,
                        }
                        response = await client.post("/api/simulator/scripts", json=payload)
                        assert response.status_code == 202, response.text
                        ids.append(response.json()["data"]["script_id"])
                        assert (await client.post("/api/simulator/scripts", json=payload)).json()[
                            "data"
                        ] == response.json()["data"]
                    async with asyncio.timeout(65):
                        await asyncio.gather(
                            *(app.state.scripts.tasks[identifier] for identifier in ids)
                        )
                    for identifier, expected in zip(
                        ids, [["normal", "overheat", "normal"], ["normal", "offline", "normal"]]
                    ):
                        result = (await client.get("/api/simulator/scripts/" + identifier)).json()[
                            "data"
                        ]
                        assert result["status"] == "completed", result
                        assert [step["scenario"] for step in result["steps_json"]] == expected
                        assert all(step["status"] == "applied" for step in result["steps_json"])
                        assert [step["offset_seconds"] for step in result["steps_json"]] == [
                            0,
                            20,
                            40,
                        ]
                        async with app.state.db.sessions() as session:
                            commands = [
                                await session.get(ScenarioCommandRow, step["command_id"])
                                for step in result["steps_json"]
                            ]
                            assert all(command.ack_at is not None for command in commands)
                            assert all(
                                19
                                <= (
                                    commands[i].requested_at - commands[i - 1].requested_at
                                ).total_seconds()
                                <= 21
                                for i in (1, 2)
                            )
                    async with app.state.db.sessions() as session:
                        assert (await session.scalars(select(DeviceCommand))).all() == []
                        assert all(
                            device.command_generation == 0
                            for device in (await session.scalars(select(Device))).all()
                        )
            finally:
                for device in devices:
                    await device.close()
