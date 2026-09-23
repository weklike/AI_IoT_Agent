"""Every new write endpoint repeats its original operation five times before guards."""

import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Alarm, OperationRequest, WorkOrderEvent
from backend.app.work_orders import WorkOrderService
from simulator.main import DeviceClient
from tests.support.evidence import seed_hot_run
from tests.support.resources import broker


async def test_all_new_write_routes_repeat_five_and_reject_changed_content(tmp_path, valid_payload):
    with broker() as (port, prefix):
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                mqtt_port=port,
                mqtt_topic_prefix=prefix,
                simulator_mode="operations",
                simulator_state_dir=str(tmp_path / "state"),
                database_url=f"sqlite+aiosqlite:///{tmp_path}/db.sqlite",
            )
        )
        devices = [DeviceClient(f"CHG-00{i}", app.state.settings) for i in (1, 2, 3)]
        request_ids = []
        async with app.router.lifespan_context(app):
            for device in devices:
                await device.start()
            try:
                async with asyncio.timeout(8):
                    while not all(
                        [
                            (await app.state.store.device_status(f"CHG-00{i}"))["data_fresh"]
                            for i in (1, 2, 3)
                        ]
                    ):
                        await asyncio.sleep(0.05)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test"
                ) as client:

                    async def repeated(method, path, values, changed=None, other_path=None):
                        body = {"request_id": str(uuid4()), **values}
                        request_ids.append(body["request_id"])
                        response = await client.request(method, path, json=body)
                        assert response.status_code in {200, 201, 202}, response.text
                        original = response.json()["data"]
                        for _ in range(5):
                            retry = await client.request(method, path, json=body)
                            assert retry.status_code == response.status_code, retry.text
                            assert retry.json()["data"] == original
                        if changed:
                            conflict = await client.request(method, path, json={**body, **changed})
                            assert conflict.status_code == 409, conflict.text
                            assert conflict.json()["error"]["code"] == "REQUEST_CONFLICT"
                        if other_path:
                            conflict = await client.request(method, other_path, json=body)
                            assert conflict.status_code == 409, conflict.text
                            assert conflict.json()["error"]["code"] == "REQUEST_CONFLICT"
                        return original

                    async def verified(command_id):
                        async with asyncio.timeout(10):
                            while True:
                                row = (
                                    await client.get("/api/device-commands/" + command_id)
                                ).json()["data"]
                                if row["verification_status"] != "pending":
                                    assert row["verification_status"] == "verified", row
                                    return
                                await asyncio.sleep(0.05)

                    start = await repeated(
                        "POST",
                        "/api/devices/CHG-001/charging/start",
                        {"requested_power_w": 20000},
                        {"requested_power_w": 10000},
                        "/api/devices/CHG-002/charging/start",
                    )
                    await verified(start["command_id"])
                    preview = await repeated(
                        "POST",
                        "/api/power-plans",
                        {"budget_w": 20000, "strategy": "equal"},
                        {"budget_w": 10000},
                    )
                    plan_id = preview["plan_id"]
                    await repeated(
                        "POST",
                        f"/api/power-plans/{plan_id}/execute",
                        {},
                        other_path=f"/api/power-plans/{uuid4()}/execute",
                    )
                    async with asyncio.timeout(10):
                        while (await client.get("/api/power-plans/" + plan_id)).json()["data"][
                            "status"
                        ] == "EXECUTING":
                            await asyncio.sleep(0.05)
                    stop = await repeated(
                        "POST",
                        "/api/devices/CHG-001/charging/stop",
                        {"session_id": start["session_id"]},
                        {"session_id": str(uuid4())},
                        "/api/devices/CHG-002/charging/stop",
                    )
                    await verified(stop["command_id"])
                    rule = (await client.get("/api/alarm-rules/CHG-002/OVERHEAT")).json()["data"]
                    await repeated(
                        "PUT",
                        "/api/alarm-rules/CHG-002/OVERHEAT",
                        {"expected_version": rule["version"], "enabled": True},
                        {"enabled": False},
                        "/api/alarm-rules/CHG-003/OVERHEAT",
                    )
                    context = await seed_hot_run(app.state.store, valid_payload)
                    async with app.state.db.sessions() as session:
                        alarm = await session.scalar(
                            select(Alarm).where(
                                Alarm.device_id == "CHG-002",
                                Alarm.reason_code == "OVERHEAT",
                                Alarm.condition == "ACTIVE",
                            )
                        )
                    await repeated(
                        "POST",
                        f"/api/alarms/{alarm.alarm_id}/acknowledge",
                        {"expected_version": alarm.version},
                        {"expected_version": alarm.version + 1},
                        f"/api/alarms/{uuid4()}/acknowledge",
                    )
                    order = await WorkOrderService(
                        app.state.db, app.state.settings, app.state.clock
                    ).create("CHG-002", "OVERHEAT", context=context)
                    order_id = order["data"]["order_id"]
                    await repeated(
                        "POST",
                        f"/api/work-orders/{order_id}/transitions",
                        {"expected_version": 1, "target_status": "IN_PROGRESS", "note": "已接收"},
                        {"note": "不同说明"},
                        f"/api/work-orders/{uuid4()}/transitions",
                    )
                    patrol = await repeated(
                        "POST", "/api/patrols", {"window_minutes": 30}, {"window_minutes": 10}
                    )
                    await app.state.scheduler.task
                    assert (await client.get("/api/patrols/" + patrol["report_id"])).json()["data"][
                        "status"
                    ] == "completed"
                    schedule = (await client.get("/api/patrol-schedule")).json()["data"]
                    await repeated(
                        "PUT",
                        "/api/patrol-schedule",
                        {"expected_version": schedule["version"], "enabled": False},
                        {"enabled": True},
                    )
                    script = await repeated(
                        "POST",
                        "/api/simulator/scripts",
                        {"device_id": "CHG-003", "script_name": "normal_overheat_normal"},
                        {"script_name": "normal_offline_normal"},
                    )
                    await repeated(
                        "POST",
                        f"/api/simulator/scripts/{script['script_id']}/cancel",
                        {},
                        other_path=f"/api/simulator/scripts/{uuid4()}/cancel",
                    )
                    async with app.state.db.sessions() as session:
                        for request_id in request_ids:
                            assert (
                                await session.scalar(
                                    select(func.count())
                                    .select_from(OperationRequest)
                                    .where(OperationRequest.request_id == request_id)
                                )
                                == 1
                            )
                        assert (
                            await session.scalar(
                                select(func.count())
                                .select_from(WorkOrderEvent)
                                .where(WorkOrderEvent.order_id == order_id)
                            )
                            == 1
                        )
            finally:
                for device in devices:
                    await device.close()
