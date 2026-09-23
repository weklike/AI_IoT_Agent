from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request

from backend.app.api import success
from backend.app.contracts import Contract

router = APIRouter(prefix="/api/simulator/scripts")


class StartScript(Contract):
    request_id: UUID
    device_id: str
    script_name: Literal["normal_overheat_normal", "normal_offline_normal"]


class CancelScript(Contract):
    request_id: UUID


@router.post("", status_code=202)
async def start(request: Request, body: StartScript):
    return success(
        request,
        await request.app.state.scripts.start(
            str(body.request_id), body.device_id, body.script_name
        ),
        202,
    )


@router.post("/{script_id}/cancel")
async def cancel(request: Request, script_id: UUID, body: CancelScript):
    return success(
        request, await request.app.state.scripts.cancel(str(body.request_id), str(script_id))
    )


@router.get("/{script_id}")
async def get(request: Request, script_id: UUID):
    return success(request, await request.app.state.scripts.get(str(script_id)))
