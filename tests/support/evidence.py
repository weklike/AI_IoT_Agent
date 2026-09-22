from uuid import uuid4

from backend.app.api import json_data
from backend.app.contracts import TelemetryMessage, ToolContext
from backend.app.models import AgentRun, ToolCall


async def seed_hot_run(store, payload, *, allowed=True, device_id="CHG-002"):
    now = store.clock.now()
    sample = TelemetryMessage.model_validate({**payload, "device_id": device_id, "ts": now})
    await store.ingest(sample, now)
    run_id, read_id, write_id = str(uuid4()), str(uuid4()), str(uuid4())
    status = await store.device_status(device_id)
    async with store.db.sessions.begin() as session:
        session.add(
            AgentRun(
                run_id=run_id,
                request_id=str(uuid4()),
                request_hash="test",
                question="test",
                allow_work_order=allowed,
                status="running",
                created_at=now,
            )
        )
        await session.flush()
        session.add(
            ToolCall(
                tool_call_id=read_id,
                provider_call_id=str(uuid4()),
                run_id=run_id,
                tool_name="get_device_status",
                args_json={"device_id": device_id},
                result_json={
                    "tool_call_id": read_id,
                    "ok": True,
                    "data": json_data(status),
                    "error": None,
                },
                status="succeeded",
                started_at=now,
                duration_ms=1,
            )
        )
        session.add(
            ToolCall(
                tool_call_id=write_id,
                provider_call_id=str(uuid4()),
                run_id=run_id,
                tool_name="create_work_order",
                args_json={"device_id": device_id, "reason_code": "OVERHEAT"},
                status="running",
                started_at=now,
            )
        )
    return ToolContext(run_id=run_id, tool_call_id=write_id, allow_work_order=allowed)
