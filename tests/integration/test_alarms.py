import json
from uuid import uuid4

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from tests.support.clock import FixedClock


async def test_alarm_ack_is_not_recovery_stale_unknown_and_fresh_clear(
    tmp_path, fixed_now, valid_payload
):
    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/alarms.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        seq = 0

        async def sample(temperature):
            nonlocal seq
            seq += 1
            payload = {
                **valid_payload,
                "message_id": str(uuid4()),
                "seq": seq,
                "ts": clock.now().isoformat(),
                "temperature_c": temperature,
            }
            assert (
                await app.state.store.receive(
                    json.dumps(payload).encode(),
                    "charge/v1/devices/CHG-002/telemetry",
                    clock.now(),
                    False,
                )
                == "accepted"
            )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await sample(59.999)
            response = await client.get("/api/alarms", params={"device_id": "CHG-002"})
            assert response.status_code == 200, response.text
            assert response.json()["data"]["items"] == []
            clock.advance(2)
            await sample(60)
            hot = (
                await client.get(
                    "/api/alarms", params={"device_id": "CHG-002", "reason": "OVERHEAT"}
                )
            ).json()["data"]["items"][0]
            assert hot["condition"] == "ACTIVE"
            body = {"request_id": str(uuid4()), "expected_version": hot["version"]}
            acknowledged = await client.post(
                f"/api/alarms/{hot['alarm_id']}/acknowledge", json=body
            )
            assert acknowledged.status_code == 200, acknowledged.text
            assert acknowledged.json()["data"]["condition"] == "ACTIVE"
            assert (
                await client.post(f"/api/alarms/{hot['alarm_id']}/acknowledge", json=body)
            ).json()["data"] == acknowledged.json()["data"]
            stale_version = await client.post(
                f"/api/alarms/{hot['alarm_id']}/acknowledge",
                json={**body, "request_id": str(uuid4())},
            )
            assert stale_version.status_code == 409
            assert stale_version.json()["error"]["code"] == "VERSION_CONFLICT"
            clock.advance(16)
            await app.state.alarms.evaluate_time()
            rows = (await client.get("/api/alarms", params={"device_id": "CHG-002"})).json()[
                "data"
            ]["items"]
            assert {row["reason_code"] for row in rows} == {"OVERHEAT", "OFFLINE"}
            assert (
                next(row for row in rows if row["reason_code"] == "OVERHEAT")["evaluation_state"]
                == "unknown"
            )
            await sample(55)
            rows = (await client.get("/api/alarms", params={"device_id": "CHG-002"})).json()[
                "data"
            ]["items"]
            assert (
                next(row for row in rows if row["reason_code"] == "OFFLINE")["condition"]
                == "CLEARED"
            )
            assert (
                next(row for row in rows if row["reason_code"] == "OVERHEAT")["condition"]
                == "ACTIVE"
            )
            for _ in range(6):
                clock.advance(2)
                await sample(54)
            rows = (await client.get("/api/alarms", params={"device_id": "CHG-002"})).json()[
                "data"
            ]["items"]
            recovered = next(row for row in rows if row["reason_code"] == "OVERHEAT")
            assert recovered["condition"] == "CLEARED"
            assert recovered["acknowledged_at"] is not None
            assert recovered["peak_temperature_c"] == 60
            assert (await client.get("/api/alarms", params={"device_id": "CHG-001"})).json()[
                "data"
            ]["items"] == []


async def test_changed_disabled_rule_preserves_active_rule_and_restart_unknown(
    tmp_path, fixed_now, valid_payload
):
    from backend.app.models import Alarm

    clock = FixedClock(fixed_now)
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/restart.db",
    )
    app = create_app(settings, clock=clock)
    async with app.router.lifespan_context(app):
        assert (
            await app.state.store.receive(
                json.dumps(valid_payload).encode(),
                "charge/v1/devices/CHG-002/telemetry",
                clock.now(),
                False,
            )
            == "accepted"
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            hot = (await client.get("/api/alarms", params={"device_id": "CHG-002"})).json()["data"][
                "items"
            ][0]
            response = await client.put(
                "/api/alarm-rules/CHG-002/OVERHEAT",
                json={
                    "request_id": str(uuid4()),
                    "expected_version": 1,
                    "enabled": False,
                    "clear_duration_seconds": 0,
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["data"]["version"] == 2
            conflict = await client.put(
                "/api/alarm-rules/CHG-002/OVERHEAT",
                json={"request_id": str(uuid4()), "expected_version": 1, "enabled": True},
            )
            assert conflict.status_code == 409
            assert (
                await client.put(
                    "/api/alarm-rules/CHG-002/OFFLINE",
                    json={
                        "request_id": str(uuid4()),
                        "expected_version": 1,
                        "clear_duration_seconds": 1,
                    },
                )
            ).status_code == 422
            assert (
                await client.put(
                    "/api/alarm-rules/CHG-002/OVERHEAT",
                    json={"request_id": str(uuid4()), "expected_version": 2, "clear_below_c": 60},
                )
            ).status_code == 422
    restarted = create_app(settings, clock=clock)
    async with restarted.router.lifespan_context(restarted):
        async with restarted.state.db.sessions() as session:
            persisted = await session.get(Alarm, hot["alarm_id"])
            assert persisted.condition == "ACTIVE" and persisted.evaluation_state == "unknown"
            assert (
                persisted.rule_json["version"] == 1
                and persisted.rule_json["clear_duration_seconds"] == 10
            )
        for index in range(6):
            clock.advance(2)
            payload = {
                **valid_payload,
                "message_id": str(uuid4()),
                "seq": 20 + index,
                "ts": clock.now().isoformat(),
                "temperature_c": 54,
            }
            await restarted.state.store.receive(
                json.dumps(payload).encode(),
                "charge/v1/devices/CHG-002/telemetry",
                clock.now(),
                False,
            )
            async with restarted.state.db.sessions() as session:
                persisted = await session.get(Alarm, hot["alarm_id"])
                assert persisted.condition == ("CLEARED" if index == 5 else "ACTIVE")
        clock.advance(2)
        payload = {
            **valid_payload,
            "message_id": str(uuid4()),
            "seq": 30,
            "ts": clock.now().isoformat(),
            "temperature_c": 72,
        }
        await restarted.state.store.receive(
            json.dumps(payload).encode(), "charge/v1/devices/CHG-002/telemetry", clock.now(), False
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted), base_url="http://test"
        ) as client:
            assert (
                await client.get(
                    "/api/alarms", params={"device_id": "CHG-002", "condition": "ACTIVE"}
                )
            ).json()["data"]["items"] == []

            restored = await client.put(
                "/api/alarm-rules/CHG-002/OVERHEAT",
                json={"request_id": str(uuid4()), "expected_version": 2, "enabled": True},
            )
            assert restored.status_code == 200 and restored.json()["data"]["version"] == 3
            clock.advance(2)
            payload.update(message_id=str(uuid4()), seq=31, ts=clock.now().isoformat())
            assert (
                await restarted.state.store.receive(
                    json.dumps(payload).encode(),
                    "charge/v1/devices/CHG-002/telemetry",
                    clock.now(),
                    False,
                )
                == "accepted"
            )
            active = (
                await client.get(
                    "/api/alarms", params={"device_id": "CHG-002", "condition": "ACTIVE"}
                )
            ).json()["data"]["items"]
            assert len(active) == 1 and active[0]["alarm_id"] != hot["alarm_id"]
            async with restarted.state.db.sessions() as session:
                assert (await session.get(Alarm, active[0]["alarm_id"])).rule_json["version"] == 3
                original = await session.get(Alarm, hot["alarm_id"])
                assert original.condition == "CLEARED" and original.rule_json["version"] == 1


async def test_persisted_trigger_duration_resets_after_out_of_order_sample(
    tmp_path, fixed_now, valid_payload
):
    from datetime import timedelta

    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/duration.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                "/api/alarm-rules/CHG-002/OVERHEAT",
                json={
                    "request_id": str(uuid4()),
                    "expected_version": 1,
                    "trigger_duration_seconds": 10,
                },
            )
            assert response.status_code == 200
            seq = 0

            async def sample(old=False):
                nonlocal seq
                seq += 1
                payload = {
                    **valid_payload,
                    "message_id": str(uuid4()),
                    "seq": seq,
                    "ts": (clock.now() - timedelta(seconds=3) if old else clock.now()).isoformat(),
                }
                await app.state.store.receive(
                    json.dumps(payload).encode(),
                    "charge/v1/devices/CHG-002/telemetry",
                    clock.now(),
                    False,
                )

            for _ in range(4):
                await sample()
                clock.advance(2)
            await sample(old=True)
            await sample()
            for _ in range(4):
                clock.advance(2)
                await sample()
                assert (await client.get("/api/alarms")).json()["data"]["items"] == []
            clock.advance(2)
            await sample()
            assert len((await client.get("/api/alarms")).json()["data"]["items"]) == 1
