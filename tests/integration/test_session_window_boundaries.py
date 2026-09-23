from datetime import timedelta

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from tests.support.clock import FixedClock
from tests.support.fixtures_v2 import load_v2_dataset


async def test_overlap_does_not_prorate_or_count_energy_before_session_end(tmp_path, fixed_now):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/windows.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "SESSION-DONE", "window-boundaries", 1)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for start, end, expected_energy, expected_ended in [
                (fixed_now - timedelta(minutes=20), fixed_now - timedelta(minutes=5), None, 0),
                (fixed_now - timedelta(minutes=1), fixed_now, 3333, 1),
                (fixed_now - timedelta(hours=24), fixed_now, 3333, 1),
            ]:
                params = {"device_id": "CHG-001", "from": start.isoformat(), "to": end.isoformat()}
                response = await client.get("/api/charging-statistics", params=params)
                assert response.status_code == 200
                data = response.json()["data"]
                assert data["session_count"] == 1
                assert data["ended_session_count"] == expected_ended
                assert data["completed_session_energy_wh"] == expected_energy
                response = await client.get("/api/charging-sessions", params=params)
                assert response.status_code == 200
                row = response.json()["data"]["items"][0]
                assert row["duration_seconds"] == 600 and row["energy_wh"] == 3333
