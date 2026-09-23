from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime
from pydantic_core import to_jsonable_python
from sqlalchemy import and_, or_, select

from backend.app.contracts import DEVICE_IDS, Contract, RunRequest, Scenario
from backend.app.errors import DomainError
from backend.app.models import AgentRun, ToolCall, WorkOrder
from backend.app.telemetry.queries import history_rows, sample_dict

router = APIRouter(prefix="/api")


def json_data(value):
    return to_jsonable_python(value)


def success(request: Request, data, status: int = 200):
    return JSONResponse(
        status_code=status,
        content={"data": json_data(data), "request_id": request.state.request_id},
    )


@router.get("/devices")
async def devices(request: Request):
    return success(
        request,
        [await request.app.state.store.device_status(device_id) for device_id in DEVICE_IDS],
    )


@router.get("/devices/{device_id}")
async def device(request: Request, device_id: str):
    return success(request, await request.app.state.store.device_status(device_id))


@router.get("/devices/{device_id}/telemetry")
async def telemetry(
    request: Request,
    device_id: str,
    start: Annotated[AwareDatetime, Query(alias="from")],
    end: Annotated[AwareDatetime, Query(alias="to")],
):
    async with request.app.state.db.sessions() as session:
        rows = await history_rows(session, device_id, start, end)
        points = []
        previous_ts = None
        interval = request.app.state.settings.telemetry_interval_seconds
        for row in rows:
            point = sample_dict(row)
            # Half an interval tolerates timer jitter; a missing expected sample breaks the line.
            point["gap_before"] = (
                previous_ts is not None and (row.ts - previous_ts).total_seconds() > interval * 1.5
            )
            points.append(point)
            previous_ts = row.ts
        return success(request, points)


class ScenarioRequest(Contract):
    device_id: str
    scenario: Scenario


@router.post("/simulator/scenarios", status_code=202)
async def scenario(request: Request, body: ScenarioRequest):
    return success(
        request, await request.app.state.scripts.manual(body.device_id, body.scenario), 202
    )


@router.get("/simulator/commands/{command_id}")
async def scenario_status(request: Request, command_id: str):
    return success(request, await request.app.state.control.get(command_id))


@router.get("/agent/runs")
async def run_history(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20, cursor: UUID | None = None
):
    async with request.app.state.db.sessions() as session:
        query = select(AgentRun)
        if cursor:
            previous = await session.get(AgentRun, str(cursor))
            if previous is None:
                raise DomainError("INVALID_ARGUMENTS", "任务游标不存在")
            query = query.where(
                or_(
                    AgentRun.created_at < previous.created_at,
                    and_(
                        AgentRun.created_at == previous.created_at,
                        AgentRun.run_id < previous.run_id,
                    ),
                )
            )
        rows = (
            await session.scalars(
                query.order_by(AgentRun.created_at.desc(), AgentRun.run_id.desc()).limit(limit + 1)
            )
        ).all()
        return success(
            request,
            {
                "items": [
                    {
                        key: getattr(row, key)
                        for key in (
                            "run_id",
                            "question",
                            "status",
                            "kind",
                            "created_at",
                            "finished_at",
                            "error_code",
                        )
                    }
                    for row in rows[:limit]
                ],
                "next_cursor": rows[limit - 1].run_id if len(rows) > limit else None,
            },
        )


@router.post("/agent/runs", status_code=202)
async def start_run(request: Request, body: RunRequest):
    if request.app.state.scheduler is None:
        raise DomainError("AGENT_UNAVAILABLE", "Agent 执行器尚未就绪", 503)
    run_id = await request.app.state.scheduler.reserve(
        str(body.request_id), body.question, body.allow_work_order
    )
    return success(request, {"run_id": run_id}, 202)


@router.get("/agent/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    async with request.app.state.db.sessions() as session:
        run = await session.get(AgentRun, run_id)
        if run is None:
            raise DomainError("RUN_NOT_FOUND", "任务不存在", 404)
        calls = (
            await session.scalars(
                select(ToolCall)
                .where(ToolCall.run_id == run_id)
                .order_by(ToolCall.ordinal, ToolCall.started_at, ToolCall.tool_call_id)
            )
        ).all()
        data = {
            key: getattr(run, key)
            for key in (
                "run_id",
                "request_id",
                "question",
                "allow_work_order",
                "status",
                "answer",
                "answer_refs",
                "kind",
                "created_at",
                "finished_at",
                "error_code",
            )
        }
        data["tool_calls"] = [
            {
                key: getattr(call, key)
                for key in (
                    "tool_call_id",
                    "provider_call_id",
                    "tool_name",
                    "args_json",
                    "result_json",
                    "status",
                    "started_at",
                    "duration_ms",
                    "error_code",
                )
            }
            for call in calls
        ]
        data["llm_mode"] = request.app.state.settings.llm_mode
        return success(request, data)


@router.get("/work-orders")
async def work_orders(
    request: Request,
    device_id: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    cursor: UUID | None = None,
    state: Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED", "UNCLOSED"] | None = None,
):
    if device_id is not None and device_id not in DEVICE_IDS:
        raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
    async with request.app.state.db.sessions() as session:
        query = select(WorkOrder).order_by(WorkOrder.created_at.desc(), WorkOrder.order_id.desc())
        if device_id:
            query = query.where(WorkOrder.device_id == device_id)
        if state:
            query = query.where(
                WorkOrder.status.in_(["OPEN", "IN_PROGRESS", "RESOLVED"])
                if state == "UNCLOSED"
                else WorkOrder.status == state
            )
        if cursor:
            if limit is None:
                raise DomainError("INVALID_ARGUMENTS", "分页游标需要limit")
            previous = await session.get(WorkOrder, str(cursor))
            if previous is None or device_id and previous.device_id != device_id:
                raise DomainError("INVALID_ARGUMENTS", "工单游标无效")
            query = query.where(
                or_(
                    WorkOrder.created_at < previous.created_at,
                    and_(
                        WorkOrder.created_at == previous.created_at,
                        WorkOrder.order_id < previous.order_id,
                    ),
                )
            )
        if limit:
            query = query.limit(limit + 1)
        rows = (await session.scalars(query)).all()
        data = [
            {
                key: getattr(row, key)
                for key in (
                    "order_id",
                    "device_id",
                    "reason_code",
                    "status",
                    "evidence_json",
                    "created_from_run_id",
                    "created_at",
                    "version",
                    "closed_at",
                    "alarm_id",
                )
            }
            for row in (rows[:limit] if limit else rows)
        ]
        return success(
            request,
            {"items": data, "next_cursor": rows[limit - 1].order_id if len(rows) > limit else None}
            if limit
            else data,
        )
