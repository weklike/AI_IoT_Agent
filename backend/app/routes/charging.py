from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, Field

from backend.app.api import success
from backend.app.charging.service import charging_statistics, get_session, list_sessions
from backend.app.contracts import Contract

router = APIRouter(prefix="/api")


class StartRequest(Contract):
    request_id: UUID
    requested_power_w: Annotated[int, Field(strict=True, ge=100, le=20000, multiple_of=100)]


class StopRequest(Contract):
    request_id: UUID
    session_id: UUID


@router.post("/devices/{device_id}/charging/start", status_code=202)
async def start(request: Request, device_id: str, body: StartRequest):
    result = await request.app.state.charging.create(
        device_id,
        str(body.request_id),
        "start_session",
        {"requested_power_w": body.requested_power_w},
    )
    return success(request, result, 202)


@router.post("/devices/{device_id}/charging/stop", status_code=202)
async def stop(request: Request, device_id: str, body: StopRequest):
    result = await request.app.state.charging.create(
        device_id, str(body.request_id), "stop_session", {"session_id": str(body.session_id)}
    )
    return success(request, result, 202)


@router.get("/device-commands/{command_id}")
async def command(request: Request, command_id: UUID):
    return success(request, await request.app.state.charging.get(str(command_id)))


@router.get("/charging-sessions")
async def sessions(
    request: Request,
    device_id: str,
    start: Annotated[AwareDatetime, Query(alias="from")],
    end: Annotated[AwareDatetime, Query(alias="to")],
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    async with request.app.state.db.sessions() as session:
        return success(
            request, await list_sessions(session, device_id, start, end, limit=limit, cursor=cursor)
        )


@router.get("/charging-statistics")
async def statistics(
    request: Request,
    device_id: str,
    start: Annotated[AwareDatetime, Query(alias="from")],
    end: Annotated[AwareDatetime, Query(alias="to")],
):
    async with request.app.state.db.sessions() as session:
        return success(request, await charging_statistics(session, device_id, start, end))


@router.get("/charging-sessions/{session_id}")
async def detail(request: Request, session_id: UUID):
    async with request.app.state.db.sessions() as session:
        return success(request, await get_session(session, str(session_id)))
