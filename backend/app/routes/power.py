from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import Field

from backend.app.api import success
from backend.app.contracts import Contract, DeviceID

router = APIRouter(prefix="/api")


class PreviewRequest(Contract):
    request_id: UUID
    budget_w: Annotated[int, Field(strict=True, ge=0, le=60000, multiple_of=100)]
    strategy: Literal["equal", "priority"]
    device_priority: list[DeviceID] | None = None


class ExecuteRequest(Contract):
    request_id: UUID


@router.post("/power-plans", status_code=201)
async def preview(request: Request, body: PreviewRequest):
    return success(
        request,
        await request.app.state.power.preview(
            str(body.request_id), body.budget_w, body.strategy, body.device_priority
        ),
        201,
    )


@router.post("/power-plans/{plan_id}/execute", status_code=202)
async def execute(request: Request, plan_id: UUID, body: ExecuteRequest):
    return success(
        request, await request.app.state.power.execute(str(body.request_id), str(plan_id)), 202
    )


@router.get("/power-plans/{plan_id}")
async def plan(request: Request, plan_id: UUID):
    return success(request, await request.app.state.power.get(str(plan_id)))


@router.get("/station-state")
async def station(request: Request):
    return success(request, await request.app.state.power.station())
