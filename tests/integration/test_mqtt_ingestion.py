import asyncio
import json

import pytest
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import DiagnosticEvent, Telemetry
from simulator.main import DeviceClient
from tests.support.mqtt import MQTTProbe
from tests.support.resources import broker


async def test_mqtt_to_database_reject_then_accept(tmp_path):
    with broker() as (port, prefix):
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                mqtt_port=port,
                mqtt_topic_prefix=prefix,
                database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
            )
        )
        probe = MQTTProbe(port, prefix)
        async with app.router.lifespan_context(app):
            await probe.start()
            device = DeviceClient("CHG-002", app.state.settings)
            try:
                async with asyncio.timeout(10):
                    while not app.state.mqtt.subscribed:
                        await asyncio.sleep(0.02)
                probe.client.publish(f"{prefix}/devices/CHG-002/telemetry", b"{bad", qos=1)
                await device.start()
                async with asyncio.timeout(6):
                    while (await app.state.store.device_status("CHG-002"))[
                        "connection_state"
                    ] != "online":
                        await asyncio.sleep(0.02)
                await device.close()
                raw = next(
                    p for t, p in probe.messages if t.endswith("/telemetry") and isinstance(p, dict)
                )
                for _ in range(9):
                    probe.client.publish(
                        f"{prefix}/devices/CHG-002/telemetry", json.dumps(raw), qos=1
                    )
                async with asyncio.timeout(5):
                    while True:
                        async with app.state.db.sessions() as session:
                            count = await session.scalar(
                                select(func.count())
                                .select_from(DiagnosticEvent)
                                .where(DiagnosticEvent.event_type == "duplicate")
                            )
                        if count == 9:
                            break
                        await asyncio.sleep(0.02)
                async with app.state.db.sessions() as session:
                    assert await session.scalar(select(func.count()).select_from(Telemetry)) == 1
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(DiagnosticEvent)
                            .where(DiagnosticEvent.event_type == "rejected")
                        )
                        == 1
                    )
            finally:
                await device.close()
                await probe.close()
        assert app.state.consumer.done()


async def test_broker_restart_resubscribes_and_preserves_history(tmp_path):
    import subprocess

    with broker() as (port, prefix):
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                mqtt_port=port,
                mqtt_topic_prefix=prefix,
                database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
            )
        )
        async with app.router.lifespan_context(app):
            device = DeviceClient("CHG-001", app.state.settings)
            await device.start()
            try:
                async with asyncio.timeout(8):
                    while (await app.state.store.device_status("CHG-001"))["message_id"] is None:
                        await asyncio.sleep(0.02)
                initial = (await app.state.store.device_status("CHG-001"))["message_id"]
                # The container name is derived from this fixture's unique project, never a developer resource.
                owned_container = prefix.split("/")[1] + "-mqtt-1"
                await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "restart", owned_container],
                    check=True,
                    capture_output=True,
                )
                async with asyncio.timeout(10):
                    while (await app.state.store.device_status("CHG-001"))["message_id"] == initial:
                        await asyncio.sleep(0.02)
                assert app.state.mqtt.subscribed
                async with app.state.db.sessions() as session:
                    assert await session.scalar(select(func.count()).select_from(Telemetry)) >= 2
            finally:
                await device.close()


@pytest.mark.parametrize("schema_version", [1, 2])
async def test_real_retained_invalid_inputs_then_valid_sample(
    tmp_path, fixed_now, valid_payload, schema_version
):
    from datetime import timedelta

    from tests.support.clock import FixedClock
    from tests.unit.test_telemetry_v2 import payload_v2

    if schema_version == 2:
        valid_payload = payload_v2(valid_payload)
    with broker() as (port, prefix):
        probe = MQTTProbe(port, prefix)
        await probe.start()
        topic = f"{prefix}/devices/CHG-002/telemetry"
        published = probe.client.publish(topic, json.dumps(valid_payload), qos=1, retain=True)
        await asyncio.to_thread(published.wait_for_publish, 3)
        app = create_app(
            Settings(
                _env_file=None,
                app_env="test",
                mqtt_port=port,
                mqtt_topic_prefix=prefix,
                database_url=f"sqlite+aiosqlite:///{tmp_path}/invalid.db",
            ),
            clock=FixedClock(fixed_now),
        )
        try:
            async with app.router.lifespan_context(app):
                async with asyncio.timeout(6):
                    while True:
                        async with app.state.db.sessions() as session:
                            retained = await session.scalar(
                                select(func.count())
                                .select_from(DiagnosticEvent)
                                .where(DiagnosticEvent.event_type == "retained")
                            )
                        if retained:
                            break
                        await asyncio.sleep(0.02)
                assert (await app.state.store.device_status("CHG-002"))[
                    "connection_state"
                ] == "unknown"
                invalid = [b"{", b"{}", b"x" * 8193]
                for field, value in [
                    ("temperature_c", "71"),
                    ("temperature_c", True),
                    ("temperature_c", float("nan")),
                    ("temperature_c", 121),
                    ("ts", (fixed_now + timedelta(seconds=6)).isoformat()),
                    ("ts", (fixed_now - timedelta(seconds=86401)).isoformat()),
                    ("device_id", "CHG-999"),
                    ("schema_version", 2 if schema_version == 1 else 3),
                    ("extra", 1),
                ]:
                    invalid.append(json.dumps({**valid_payload, field: value}).encode())
                for payload in invalid:
                    probe.client.publish(topic, payload, qos=1)
                probe.client.publish(
                    f"{prefix}/devices/CHG-001/telemetry", json.dumps(valid_payload), qos=1
                )
                probe.client.publish(topic, json.dumps(valid_payload), qos=1, retain=False)
                async with asyncio.timeout(6):
                    while (await app.state.store.device_status("CHG-002"))[
                        "connection_state"
                    ] != "online":
                        await asyncio.sleep(0.02)
                async with app.state.db.sessions() as session:
                    assert await session.scalar(select(func.count()).select_from(Telemetry)) == 1
                    rejected = await session.scalar(
                        select(func.count())
                        .select_from(DiagnosticEvent)
                        .where(DiagnosticEvent.event_type == "rejected")
                    )
                    assert rejected == len(invalid) + 1
        finally:
            await probe.close()
