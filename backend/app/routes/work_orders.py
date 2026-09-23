from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import and_, or_, select

from backend.app.api import success
from backend.app.contracts import Contract
from backend.app.errors import DomainError
from backend.app.models import WorkOrder, WorkOrderEvent
from backend.app.work_orders import WorkOrderService

router = APIRouter(prefix="/api")


class TransitionRequest(Contract):
    request_id: UUID
    expected_version: Annotated[int, Field(strict=True, ge=1)]
    target_status: Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]
    note: Annotated[str, Field(strict=True, max_length=2000)] = ""


@router.post("/work-orders/{order_id}/transitions")
async def transition(request: Request, order_id: UUID, body: TransitionRequest):
    service = WorkOrderService(
        request.app.state.db, request.app.state.settings, request.app.state.clock
    )
    return success(
        request,
        await service.transition(
            str(order_id),
            str(body.request_id),
            body.expected_version,
            body.target_status,
            body.note,
        ),
    )


@router.get("/work-orders/{order_id}/events")
async def events(
    request: Request,
    order_id: UUID,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    async with request.app.state.db.sessions() as session:
        if await session.get(WorkOrder, str(order_id)) is None:
            raise DomainError("WORK_ORDER_NOT_FOUND", "工单不存在", 404)
        filters = [WorkOrderEvent.order_id == str(order_id)]
        if cursor:
            previous = await session.get(WorkOrderEvent, str(cursor))
            if previous is None or previous.order_id != str(order_id):
                raise DomainError("INVALID_ARGUMENTS", "工单事件游标无效")
            filters.append(
                or_(
                    WorkOrderEvent.checked_at < previous.checked_at,
                    and_(
                        WorkOrderEvent.checked_at == previous.checked_at,
                        WorkOrderEvent.event_id < previous.event_id,
                    ),
                )
            )
        rows = (
            await session.scalars(
                select(WorkOrderEvent)
                .where(*filters)
                .order_by(WorkOrderEvent.checked_at.desc(), WorkOrderEvent.event_id.desc())
                .limit(limit + 1)
            )
        ).all()
        return success(
            request,
            {
                "items": [
                    {column.name: getattr(row, column.name) for column in row.__table__.columns}
                    for row in rows[:limit]
                ],
                "next_cursor": rows[limit - 1].event_id if len(rows) > limit else None,
            },
        )
