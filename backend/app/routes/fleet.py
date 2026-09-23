from typing import Annotated

from fastapi import APIRouter, Query, Request

from backend.app.api import success

router = APIRouter(prefix="/api")


@router.get("/fleet-overview")
async def fleet(request: Request, window_minutes: Annotated[int, Query(ge=1, le=60)] = 30):
    return success(request, await request.app.state.read_queries.fleet(window_minutes))
