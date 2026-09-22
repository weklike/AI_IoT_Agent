from datetime import timedelta
from uuid import uuid4

import httpx
import pytest

from backend.app.config import Settings
from backend.app.contracts import TelemetryMessage
from backend.app.main import create_app
from tests.support.clock import FixedClock


@pytest.fixture
async def app_client(tmp_path, fixed_now):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        ),
        clock=FixedClock(fixed_now),
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield app, client


async def test_devices_empty_and_unknown(app_client):
    app, client = app_client
    response = await client.get("/api/devices")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 3
    assert response.json()["data"][0]["temperature_c"] is None
    missing = await client.get("/api/devices/CHG-999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DEVICE_NOT_FOUND"


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-09-22T08:10:00Z", "to": "2026-09-22T08:00:00Z"},
        {"from": "2026-09-22T08:00:00", "to": "2026-09-22T08:10:00Z"},
        {"from": "2026-09-20T08:00:00Z", "to": "2026-09-22T08:10:00Z"},
        {},
    ],
)
async def test_bad_history_window(app_client, params):
    response = await app_client[1].get("/api/devices/CHG-002/telemetry", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ARGUMENTS"
    assert response.json()["request_id"]


async def test_history_and_statistics_full_window(app_client, valid_payload, fixed_now):
    app, client = app_client
    for seq, temperature in enumerate([58, 61, 65, 70, 72], 1):
        ts = fixed_now - timedelta(seconds=10 - seq * 2)
        sample = TelemetryMessage.model_validate(
            {
                **valid_payload,
                "message_id": str(uuid4()),
                "seq": seq,
                "ts": ts,
                "temperature_c": temperature,
            }
        )
        await app.state.store.ingest(sample, ts)
    params = {"from": (fixed_now - timedelta(minutes=10)).isoformat(), "to": fixed_now.isoformat()}
    response = await client.get("/api/devices/CHG-002/telemetry", params=params)
    assert response.status_code == 200
    points = response.json()["data"]
    assert len(points) == 5
    assert points[-1]["sample_ts"].endswith("Z")
    stats = await app.state.store.history("CHG-002", 10)
    assert stats["temperature_avg_c"] == 65.2
    assert stats["temperature_max_c"] == 72
    assert stats["overheat_count"] == 4
    assert (await client.get("/api/devices/CHG-001/telemetry", params=params)).json()["data"] == []


async def test_history_5001_rows_rejected(app_client, valid_payload, fixed_now):
    from backend.app.models import Telemetry

    app, client = app_client
    payload = TelemetryMessage.model_validate(valid_payload).model_dump()
    payload["boot_id"] = str(payload["boot_id"])
    async with app.state.db.sessions.begin() as session:
        session.add_all(
            [
                Telemetry(
                    **{
                        **payload,
                        "message_id": str(uuid4()),
                        "seq": i + 1,
                        "ts": fixed_now - timedelta(milliseconds=i),
                        "received_at": fixed_now,
                    }
                )
                for i in range(5001)
            ]
        )
    response = await client.get(
        "/api/devices/CHG-002/telemetry",
        params={
            "from": (fixed_now - timedelta(minutes=10)).isoformat(),
            "to": fixed_now.isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "HISTORY_LIMIT_EXCEEDED"
