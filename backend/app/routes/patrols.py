from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import and_, or_, select

from backend.app.api import success
from backend.app.contracts import Contract
from backend.app.errors import DomainError
from backend.app.models import PatrolReport

router = APIRouter(prefix="/api")


class PatrolRequest(Contract):
    request_id: UUID
    window_minutes: Annotated[int, Field(strict=True)]


def report_data(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@router.post("/patrols", status_code=202)
async def create(request: Request, body: PatrolRequest):
    return success(
        request,
        await request.app.state.scheduler.reserve_patrol(str(body.request_id), body.window_minutes),
        202,
    )


@router.get("/patrols")
async def listing(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20, cursor: UUID | None = None
):
    async with request.app.state.db.sessions() as session:
        query = select(PatrolReport)
        if cursor:
            anchor = await session.get(PatrolReport, str(cursor))
            if anchor is None:
                raise DomainError("INVALID_ARGUMENTS", "巡检游标不存在", 422)
            query = query.where(
                or_(
                    PatrolReport.created_at < anchor.created_at,
                    and_(
                        PatrolReport.created_at == anchor.created_at,
                        PatrolReport.report_id < anchor.report_id,
                    ),
                )
            )
        rows = (
            await session.scalars(
                query.order_by(PatrolReport.created_at.desc(), PatrolReport.report_id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
        return success(
            request,
            {
                "items": [report_data(row) for row in rows[:limit]],
                "next_cursor": rows[limit - 1].report_id if len(rows) > limit else None,
            },
        )


@router.get("/patrols/{report_id}")
async def get(request: Request, report_id: UUID):
    async with request.app.state.db.sessions() as session:
        row = await session.get(PatrolReport, str(report_id))
        if row is None:
            raise DomainError("REPORT_NOT_FOUND", "巡检报告不存在", 404)
        return success(request, report_data(row))


class ScheduleRequest(Contract):
    request_id: UUID
    expected_version: Annotated[int, Field(strict=True, ge=1)]
    enabled: Annotated[bool, Field(strict=True)]


@router.get("/patrol-schedule")
async def get_schedule(request: Request):
    return success(request, await request.app.state.patrols.get())


@router.put("/patrol-schedule")
async def put_schedule(request: Request, body: ScheduleRequest):
    return success(
        request,
        await request.app.state.patrols.change(
            str(body.request_id), body.expected_version, body.enabled
        ),
    )
