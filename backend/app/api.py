from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime
from sqlalchemy import select

from backend.app.contracts import DEVICE_IDS, Contract, RunRequest, Scenario
from backend.app.errors import DomainError
from backend.app.models import AgentRun, ToolCall, WorkOrder
from backend.app.telemetry.queries import history_rows, sample_dict

router = APIRouter(prefix="/api")


def json_data(value):
    return jsonable_encoder(
        value, custom_encoder={datetime: lambda dt: dt.isoformat().replace("+00:00", "Z")}
    )


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
        return success(request, [sample_dict(row) for row in rows])


class ScenarioRequest(Contract):
    device_id: str
    scenario: Scenario


@router.post("/simulator/scenarios", status_code=202)
async def scenario(request: Request, body: ScenarioRequest):
    return success(
        request, await request.app.state.control.create(body.device_id, body.scenario), 202
    )


@router.get("/simulator/commands/{command_id}")
async def scenario_status(request: Request, command_id: str):
    return success(request, await request.app.state.control.get(command_id))


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
                .order_by(ToolCall.started_at, ToolCall.tool_call_id)
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
async def work_orders(request: Request, device_id: str | None = None):
    if device_id is not None and device_id not in DEVICE_IDS:
        raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
    async with request.app.state.db.sessions() as session:
        query = select(WorkOrder).order_by(WorkOrder.created_at.desc())
        if device_id:
            query = query.where(WorkOrder.device_id == device_id)
        rows = (await session.scalars(query)).all()
        return success(
            request,
            [
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
                    )
                }
                for row in rows
            ],
        )
