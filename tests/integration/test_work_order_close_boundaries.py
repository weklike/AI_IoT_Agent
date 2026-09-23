import json
from uuid import uuid4

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from tests.support.clock import FixedClock
from tests.support.fixtures_v2 import load_v2_dataset


async def test_offline_order_needs_fresh_recovery_of_its_own_device(
    tmp_path, fixed_now, valid_payload
):
    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            llm_mode="fixture",
            database_url=f"sqlite+aiosqlite:///{tmp_path}/close.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "BASE", "offline-close", 1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            accepted = await client.post(
                "/api/agent/runs",
                json={
                    "request_id": str(uuid4()),
                    "question": "检查3号桩离线并创建检修工单",
                    "allow_work_order": True,
                },
            )
            assert accepted.status_code == 202
            await app.state.scheduler.task
            orders = (await client.get("/api/work-orders")).json()["data"]
            assert len(orders) == 1 and orders[0]["device_id"] == "CHG-003"
            identity = orders[0]["order_id"]

            async def transition(version, status, note=""):
                return await client.post(
                    f"/api/work-orders/{identity}/transitions",
                    json={
                        "request_id": str(uuid4()),
                        "expected_version": version,
                        "target_status": status,
                        "note": note,
                    },
                )

            assert (await transition(1, "IN_PROGRESS")).status_code == 200
            assert (await transition(2, "RESOLVED", "待核对新鲜设备恢复证据")).status_code == 200

            async def sample(device):
                payload = {
                    **valid_payload,
                    "device_id": device,
                    "message_id": str(uuid4()),
                    "boot_id": str(uuid4()),
                    "seq": 1,
                    "temperature_c": 39,
                    "ts": clock.now().isoformat(),
                }
                assert (
                    await app.state.store.receive(
                        json.dumps(payload).encode(),
                        f"charge/v1/devices/{device}/telemetry",
                        clock.now(),
                        False,
                    )
                    == "accepted"
                )
                return payload

            clock.advance(2)
            await sample("CHG-001")
            refused = await transition(3, "CLOSED")
            assert (
                refused.status_code == 409
                and refused.json()["error"]["code"] == "RECOVERY_NOT_CONFIRMED"
            )
            await sample("CHG-003")
            clock.advance(11)
            await sample("CHG-001")
            assert (await transition(3, "CLOSED")).status_code == 409
            clock.advance(1)
            recovered = await sample("CHG-003")
            closed = await transition(3, "CLOSED")
            assert closed.status_code == 200 and closed.json()["data"]["status"] == "CLOSED"
            events = (await client.get(f"/api/work-orders/{identity}/events")).json()["data"][
                "items"
            ]
            evidence = next(x for x in events if x["to_status"] == "CLOSED")["evidence_json"]
            assert (
                evidence["device_id"] == "CHG-003"
                and evidence["message_id"] == recovered["message_id"]
            )
