from uuid import uuid4

import httpx
from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import ChargingSession, DeviceCommand
from tests.support.clock import FixedClock
from tests.support.fixtures_v2 import load_v2_dataset


async def test_disconnected_control_returns_503_and_active_session_cannot_start_again(
    tmp_path, fixed_now, monkeypatch
):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/availability.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/devices/CHG-001/charging/start",
                json={"request_id": str(uuid4()), "requested_power_w": 20000},
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "MQTT_UNAVAILABLE"
            async with app.state.db.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(ChargingSession)) == 0
                assert await session.scalar(select(func.count()).select_from(DeviceCommand)) == 0
            await load_v2_dataset(app, "POWER-EQUAL", "active-start-reject", 1)

            class Publisher:
                connected = True

                def publish(self, *args):
                    raise AssertionError("Rejected start must not publish")

            monkeypatch.setattr(app.state.charging, "mqtt", Publisher())
            response = await client.post(
                "/api/devices/CHG-001/charging/start",
                json={"request_id": str(uuid4()), "requested_power_w": 20000},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "SESSION_CONFLICT"
            async with app.state.db.sessions() as session:
                assert await session.scalar(select(func.count()).select_from(ChargingSession)) == 3
