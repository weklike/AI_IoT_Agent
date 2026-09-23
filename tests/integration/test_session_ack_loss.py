import asyncio
import json

from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import SessionReport
from simulator.main import DeviceClient
from tests.support.mqtt import MQTTProbe
from tests.support.resources import broker


async def test_lost_application_ack_retries_same_report_without_duplicate_storage(
    tmp_path, monkeypatch
):
    from uuid import uuid4

    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=port,
            mqtt_topic_prefix=prefix,
            simulator_mode="operations",
            simulator_state_dir=str(tmp_path / "state"),
            database_url=f"sqlite+aiosqlite:///{tmp_path}/ack-loss.db",
        )
        app = create_app(settings)
        device = DeviceClient("CHG-001", settings)
        probe = MQTTProbe(port, prefix)
        async with app.router.lifespan_context(app):
            original = app.state.mqtt.publish
            lost = []

            def drop_first_ack(topic, payload):
                if topic.endswith("/session/ack") and not lost:
                    lost.append(json.loads(payload))
                    return True
                return original(topic, payload)

            monkeypatch.setattr(app.state.mqtt, "publish", drop_first_ack)
            await probe.start()
            await device.start()
            try:
                async with asyncio.timeout(8):
                    while not (await app.state.store.device_status("CHG-001"))["data_fresh"]:
                        await asyncio.sleep(0.02)
                await app.state.charging.create(
                    "CHG-001", str(uuid4()), "start_session", {"requested_power_w": 20000}
                )
                async with asyncio.timeout(8):
                    while not lost:
                        await asyncio.sleep(0.02)
                report_id = lost[0]["report_id"]
                assert lost[0]["status"] == "stored"
                await probe.wait_for(
                    lambda t, p: t.endswith("/session/ack") and p.get("report_id") == report_id
                )
                deliveries = [
                    p
                    for t, p in probe.messages
                    if t.endswith("/session/report") and p.get("report_id") == report_id
                ]
                assert len(deliveries) >= 2 and all(p == deliveries[0] for p in deliveries)
                async with app.state.db.sessions() as session:
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(SessionReport)
                            .where(SessionReport.report_id == report_id)
                        )
                        == 1
                    )
                async with asyncio.timeout(2):
                    while any(
                        p["payload"]["report_id"] == report_id
                        for p in device.charging.state["pending_reports"]
                    ):
                        await asyncio.sleep(0.02)
            finally:
                await device.close()
                await probe.close()
