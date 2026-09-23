from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request

from backend.app.api import success
from backend.app.timeline import TimelineService

router = APIRouter(prefix="/api")


@router.get("/devices/{device_id}/timeline")
async def timeline(
    request: Request,
    device_id: str,
    start: Annotated[datetime, Query(alias="from")],
    end: Annotated[datetime, Query(alias="to")],
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
):
    return success(
        request,
        await TimelineService(request.app.state.db).query(
            device_id, start, end, limit=limit, cursor=cursor
        ),
    )
