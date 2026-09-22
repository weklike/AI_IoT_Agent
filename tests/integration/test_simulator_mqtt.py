import asyncio
import json
from pathlib import Path
from uuid import uuid4

from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS, ScenarioCommand
from simulator.main import DeviceClient
from tests.support.mqtt import MQTTProbe
from tests.support.resources import broker


async def test_three_clients_60_seconds_and_control():
    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None, app_env="test", mqtt_port=port, mqtt_topic_prefix=prefix
        )
        probe = MQTTProbe(port, prefix)
        devices = [DeviceClient(device, settings) for device in DEVICE_IDS]
        try:
            await probe.start()
            for device in devices:
                await device.start()
            assert len({device.client_id for device in devices}) == 3
            await asyncio.sleep(60)
            samples = [
                (topic, payload)
                for topic, payload in probe.messages
                if topic.endswith("/telemetry")
            ]
            for device_id in DEVICE_IDS:
                records = [p for t, p in samples if p["device_id"] == device_id]
                assert 29 <= len({p["message_id"] for p in records}) <= 31
                assert all(t == f"{prefix}/devices/{p['device_id']}/telemetry" for t, p in samples)
                assert all(35 <= p["temperature_c"] <= 40 for p in records)
            command = ScenarioCommand(command_id=uuid4(), device_id="CHG-002", scenario="overheat")
            topic = f"{prefix}/devices/CHG-002/scenario/set"
            probe.client.publish(topic, command.model_dump_json(), qos=1)
            ack = await probe.wait_for(
                lambda t, p: t.endswith("/ack") and p["command_id"] == str(command.command_id)
            )
            assert ack["status"] == "applied"
            await probe.wait_for(
                lambda t, p: (
                    t.endswith("/telemetry")
                    and p["device_id"] == "CHG-002"
                    and p["temperature_c"] >= 68
                ),
                4,
            )
            probe.client.publish(topic, command.model_dump_json(), qos=1)
            async with asyncio.timeout(4):
                while (
                    sum(
                        t.endswith("/ack") and p.get("command_id") == str(command.command_id)
                        for t, p in probe.messages
                    )
                    < 2
                ):
                    await asyncio.sleep(0.02)
            assert [
                p
                for t, p in probe.messages
                if t.endswith("/ack") and p["command_id"] == str(command.command_id)
            ] == [ack, ack]
            for scenario in ("offline", "normal"):
                next_command = command.model_copy(
                    update={"command_id": uuid4(), "scenario": scenario}
                )
                probe.client.publish(topic, next_command.model_dump_json(), qos=1)
                await probe.wait_for(
                    lambda t, p: (
                        t.endswith("/ack") and p["command_id"] == str(next_command.command_id)
                    )
                )
                if scenario == "offline":
                    await asyncio.sleep(0.1)
                    count = sum(
                        t.endswith("/telemetry") and p["device_id"] == "CHG-002"
                        for t, p in probe.messages
                    )
                    await asyncio.sleep(2.2)
                    assert (
                        sum(
                            t.endswith("/telemetry") and p["device_id"] == "CHG-002"
                            for t, p in probe.messages
                        )
                        == count
                    )
            old_boots = {device.device.device_id: device.device.boot_id for device in devices}
            for device in devices:
                await device.close()
            devices = [DeviceClient(device, settings) for device in DEVICE_IDS]
            for device in devices:
                await device.start()
                assert device.device.boot_id != old_boots[device.device.device_id]
            for device in devices:
                first = await probe.wait_for(
                    lambda t, p: (
                        t.endswith("/telemetry") and p["boot_id"] == str(device.device.boot_id)
                    ),
                    4,
                )
                assert first["seq"] == 1
            Path("artifacts/acceptance/task2/mqtt-samples.json").write_text(
                json.dumps(
                    {
                        "normal_window_seconds": 60,
                        "client_ids": [device.client_id for device in devices],
                        "messages": probe.messages,
                    },
                    indent=2,
                )
            )
        finally:
            for device in devices:
                await device.close()
            await probe.close()
