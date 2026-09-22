from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from backend.app.contracts import DEVICE_IDS, Contract, Scenario
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
