from typing import Annotated

from fastapi import APIRouter, Query, Request

from backend.app.api import success

router = APIRouter(prefix="/api")


@router.get("/knowledge/search")
async def search(
    request: Request,
    query: Annotated[str, Query(min_length=1, max_length=300)],
    device_id: str | None = None,
):
    return success(request, await request.app.state.knowledge.search(query, device_id))


@router.get("/knowledge/sources/{source_id}/versions/{version}")
async def source(request: Request, source_id: str, version: str):
    return success(request, await request.app.state.knowledge.source(source_id, version))
