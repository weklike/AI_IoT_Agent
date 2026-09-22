from uuid import uuid4

from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import AgentRun, ScenarioCommandRow, ToolCall, WorkOrder
from tests.support.clock import FixedClock


async def test_restart_interrupts_pending_runs_preserves_order_and_history(tmp_path, fixed_now):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/recover.db",
    )
    db = Database(settings)
    clock = FixedClock(fixed_now)
    await db.initialize(clock)
    run_id, call_id, order_id, command_id = [str(uuid4()) for _ in range(4)]
    async with db.sessions.begin() as session:
        session.add(
            AgentRun(
                run_id=run_id,
                request_id=str(uuid4()),
                request_hash="x",
                question="x",
                allow_work_order=True,
                status="running",
                created_at=fixed_now,
            )
        )
        await session.flush()
        session.add(
            WorkOrder(
                order_id=order_id,
                device_id="CHG-002",
                reason_code="OVERHEAT",
                status="OPEN",
                evidence_json={"test": True},
                created_from_run_id=run_id,
                created_at=fixed_now,
            )
        )
        session.add(
            ToolCall(
                tool_call_id=call_id,
                provider_call_id="p1",
                run_id=run_id,
                tool_name="create_work_order",
                args_json={},
                status="succeeded",
                started_at=fixed_now,
                result_json={"ok": True, "data": {"order_id": order_id}},
            )
        )
        session.add(
            ScenarioCommandRow(
                command_id=command_id,
                device_id="CHG-002",
                scenario="normal",
                status="pending",
                requested_at=fixed_now,
            )
        )
    await db.close()
    db = Database(settings)
    await db.initialize(clock)
    try:
        async with db.sessions() as session:
            assert (await session.get(AgentRun, run_id)).status == "interrupted"
            assert (await session.get(WorkOrder, order_id)).order_id == order_id
            assert (await session.get(ToolCall, call_id)).status == "succeeded"
            assert (await session.get(ScenarioCommandRow, command_id)).status == "timed_out"
    finally:
        await db.close()


def test_four_service_dependency_recovery(tmp_path):
    import subprocess
    import time

    import httpx

    from tests.support.resources import stack

    def wait(predicate, timeout=10):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            try:
                result = predicate()
                if result:
                    return result
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise AssertionError("Recovery deadline exceeded")

    with stack(tmp_path / "logs") as ports:
        project = ports["PROJECT"]

        def docker(*args):
            return subprocess.run(
                ["docker", *args], check=True, capture_output=True, text=True, timeout=30
            )

        base = "http://127.0.0.1:" + ports["BACKEND_PUBLISH_PORT"]
        with httpx.Client(base_url=base, timeout=2) as client:

            def device():
                response = client.get("/api/devices/CHG-002")
                response.raise_for_status()
                return response.json()["data"]

            wait(lambda: device()["connection_state"] == "online")
            original = device()["message_id"]
            # Broker remains down for the specified 10-second disruption.
            docker("stop", f"{project}-mqtt-1")
            time.sleep(10)
            # Starting the backend while the Broker is absent must not abort its lifecycle.
            docker("restart", f"{project}-backend-1")
            wait(lambda: client.get("/api/health").status_code == 503)
            assert device()["connection_state"] == "unknown"
            docker("start", f"{project}-mqtt-1")
            wait(lambda: client.get("/api/health").status_code == 200)
            wait(
                lambda: (
                    device()["message_id"] != original and device()["connection_state"] == "online"
                )
            )
            latest = device()["message_id"]
            docker("stop", f"{project}-simulator-1")
            docker("restart", f"{project}-backend-1")
            wait(lambda: client.get("/api/health").status_code == 200)
            assert device()["connection_state"] == "unknown"
            assert device()["message_id"] == latest
            docker("start", f"{project}-simulator-1")
            wait(
                lambda: (
                    device()["message_id"] != latest and device()["connection_state"] == "online"
                )
            )
            assert device()["data_fresh"] is True
