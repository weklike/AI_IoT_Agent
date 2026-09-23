from datetime import timedelta
from uuid import UUID

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import ChargingSession
from tests.support.clock import FixedClock


async def test_sessions_full_window_statistics_and_stable_pagination(tmp_path, fixed_now):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/sessions.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        async with app.state.db.sessions.begin() as session:
            for number in range(1, 4):
                session.add(
                    ChargingSession(
                        session_id=str(UUID(int=number)),
                        device_id="CHG-001",
                        status="COMPLETED",
                        requested_power_w=20000,
                        started_at=fixed_now - timedelta(minutes=20),
                        ended_at=fixed_now,
                        observed_at=fixed_now,
                        start_meter_wh=10000,
                        end_meter_wh=13333,
                        energy_wh=3333,
                        report_seq=2,
                        meter_quality="exact",
                        end_reason="USER_STOP",
                    )
                )
            session.add(
                ChargingSession(
                    session_id=str(UUID(int=4)),
                    device_id="CHG-001",
                    status="ACTIVE",
                    requested_power_w=20000,
                    started_at=fixed_now - timedelta(minutes=5),
                    observed_at=fixed_now,
                    energy_wh=500,
                    report_seq=1,
                    meter_quality="exact",
                )
            )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            params = {
                "device_id": "CHG-001",
                "from": (fixed_now - timedelta(minutes=10)).isoformat(),
                "to": fixed_now.isoformat(),
                "limit": 2,
            }
            first = await client.get("/api/charging-sessions", params=params)
            assert first.status_code == 200, first.text
            data = first.json()["data"]
            second = await client.get(
                "/api/charging-sessions", params={**params, "cursor": data["next_cursor"]}
            )
            assert second.status_code == 200, second.text
            rows = data["items"] + second.json()["data"]["items"]
            assert len({row["session_id"] for row in rows}) == 4
            assert second.json()["data"]["next_cursor"] is None
            stats = await client.get(
                "/api/charging-statistics",
                params={key: value for key, value in params.items() if key != "limit"},
            )
            assert stats.status_code == 200, stats.text
            summary = stats.json()["data"]
            assert summary["completed_session_energy_wh"] == 9999
            assert summary["session_count"] == 4
            assert summary["active_count"] == 1
            assert summary["missing_report_count"] == 0
            assert (
                await client.get(
                    "/api/charging-sessions", params={**params, "cursor": "not-a-cursor"}
                )
            ).status_code == 422
            assert (
                await client.get(
                    "/api/charging-sessions",
                    params={**params, "from": (fixed_now - timedelta(hours=25)).isoformat()},
                )
            ).status_code == 422
            assert (
                await client.get(
                    "/api/charging-sessions", params={**params, "device_id": "CHG-999"}
                )
            ).status_code == 404
            empty = await client.get(
                "/api/charging-statistics", params={**params, "device_id": "CHG-003"}
            )
            assert empty.json()["data"]["completed_session_energy_wh"] is None
            assert empty.json()["data"]["session_count"] == 0
