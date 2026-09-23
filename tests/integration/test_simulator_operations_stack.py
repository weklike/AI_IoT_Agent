"""The operations simulator volume survives an actual owned-container SIGKILL."""

import asyncio
import json
import subprocess
from datetime import timedelta
from uuid import uuid4

import httpx

from backend.app.clocks import DataClock
from tests.support.mqtt import MQTTProbe
from tests.support.resources import stack


async def test_owned_four_service_operations_volume_survives_kill(tmp_path):
    with stack(output=tmp_path / "stack", operations=True) as ports:
        project = ports["PROJECT"]
        prefix = f"charge-test/{project}/v1"
        probe = MQTTProbe(int(ports["MQTT_PUBLISH_PORT"]), prefix)
        await probe.start()
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{ports['BACKEND_PUBLISH_PORT']}"
            ) as client:
                async with asyncio.timeout(12):
                    while True:
                        response = await client.get("/api/devices")
                        rows = response.json()["data"]
                        if all(row.get("schema_version") == 2 for row in rows):
                            break
                        await asyncio.sleep(0.1)
                assert len(rows) == 3
                assert all(row["session_state"] == "IDLE" and row["power_kw"] == 0 for row in rows)
            session_id = str(uuid4())
            for generation, action, args in [
                (1, "start_session", {"session_id": session_id, "requested_power_w": 20000}),
                (2, "set_power_limit", {"power_limit_w": 20000}),
            ]:
                now = DataClock().now()
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
                    lambda t, p: (
                        t.endswith("/CHG-001/control/ack") and p.get("generation") == generation
                    )
                )
                assert ack["status"] == "applied"
            sample = await probe.wait_for(
                lambda t, p: t.endswith("/CHG-001/telemetry") and p.get("meter_total_wh", 0) > 0
            )
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "kill", f"{project}-simulator-1"],
                check=True,
                capture_output=True,
            )
            probe.messages.clear()
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "start", f"{project}-simulator-1"],
                check=True,
                capture_output=True,
            )
            terminal = await probe.wait_for(
                lambda t, p: (
                    t.endswith("/CHG-001/session/report") and p.get("status") == "INTERRUPTED"
                ),
                timeout=12,
            )
            assert terminal["end_reason"] == "SIMULATOR_RESTART"
            assert terminal["meter_quality"] == "checkpoint"
            assert terminal["end_meter_wh"] >= sample["meter_total_wh"]
            fresh = await probe.wait_for(lambda t, p: t.endswith("/CHG-001/telemetry"))
            assert fresh["meter_total_wh"] == terminal["end_meter_wh"]
            assert fresh["power_kw"] == 0
        finally:
            await probe.close()
