import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DeviceCommand, ScenarioCommandRow
from simulator.main import DeviceClient
from tests.support.resources import broker


async def test_cancel_manual_override_missing_ack_and_restart_stop_remaining_steps(tmp_path):
    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=port,
            mqtt_topic_prefix=prefix,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/boundaries.db",
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            devices = [DeviceClient(identifier, settings) for identifier in ("CHG-001", "CHG-002")]
            for device in devices:
                await device.start()
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:
                    ids = []
                    for device_id in ("CHG-001", "CHG-002", "CHG-003"):
                        response = await client.post(
                            "/api/simulator/scripts",
                            json={
                                "request_id": str(uuid4()),
                                "device_id": device_id,
                                "script_name": "normal_overheat_normal",
                            },
                        )
                        assert response.status_code == 202, response.text
                        ids.append(response.json()["data"]["script_id"])
                    async with asyncio.timeout(8):
                        while True:
                            reports = [
                                await app.state.scripts.get(identifier) for identifier in ids[:2]
                            ]
                            if all(
                                row["steps_json"] and row["steps_json"][0]["status"] == "applied"
                                for row in reports
                            ):
                                break
                            await asyncio.sleep(0.05)
                    cancel_body = {"request_id": str(uuid4())}
                    cancelled = await client.post(
                        f"/api/simulator/scripts/{ids[0]}/cancel", json=cancel_body
                    )
                    assert (
                        cancelled.status_code == 200
                        and cancelled.json()["data"]["status"] == "cancelled"
                    )
                    assert (
                        await client.post(
                            f"/api/simulator/scripts/{ids[0]}/cancel", json=cancel_body
                        )
                    ).json()["data"] == cancelled.json()["data"]
                    override = await client.post(
                        "/api/simulator/scenarios",
                        json={"device_id": "CHG-002", "scenario": "overheat"},
                    )
                    assert override.status_code == 202
                    async with asyncio.timeout(7):
                        while (await app.state.scripts.get(ids[2]))["status"] == "running":
                            await asyncio.sleep(0.1)
                    assert (await app.state.scripts.get(ids[2]))["status"] == "failed"
                    await asyncio.sleep(20.2)
                    reports = [await app.state.scripts.get(identifier) for identifier in ids]
                    assert [row["status"] for row in reports] == [
                        "cancelled",
                        "cancelled",
                        "failed",
                    ]
                    assert reports[1]["cancel_reason"] == "MANUAL_SCENARIO_OVERRIDE"
                    assert all(len(row["steps_json"]) == 1 for row in reports)
                    async with app.state.db.sessions() as session:
                        commands = (await session.scalars(select(ScenarioCommandRow))).all()
                        assert len(commands) == 4
                        assert (await session.scalars(select(DeviceCommand))).all() == []
                    pending = await app.state.scripts.start(
                        str(uuid4()), "CHG-001", "normal_offline_normal"
                    )
                    async with asyncio.timeout(5):
                        while not (await app.state.scripts.get(pending["script_id"]))["steps_json"]:
                            await asyncio.sleep(0.05)
            finally:
                for device in devices:
                    await device.close()
        restarted = create_app(settings)
        async with restarted.router.lifespan_context(restarted):
            report = await restarted.state.scripts.get(pending["script_id"])
            assert report["status"] == "interrupted"
            assert restarted.state.scripts.tasks == {}
            assert len(report["steps_json"]) == 1
