from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import and_, or_, select

from backend.app.alarms.service import alarm_data
from backend.app.api import success
from backend.app.contracts import Contract, ReasonCode
from backend.app.errors import DomainError
from backend.app.models import Alarm, Device

router = APIRouter(prefix="/api")


class VersionedRequest(Contract):
    request_id: UUID
    expected_version: Annotated[int, Field(strict=True, ge=1)]


class RuleChange(VersionedRequest):
    enabled: Annotated[bool, Field(strict=True)] | None = None
    trigger_duration_seconds: Annotated[int, Field(strict=True, ge=0, le=60)] | None = None
    clear_below_c: (
        Annotated[float, Field(strict=True, ge=-20, lt=60, allow_inf_nan=False)] | None
    ) = None
    clear_duration_seconds: Annotated[int, Field(strict=True, ge=0, le=60)] | None = None


@router.get("/alarms")
async def alarms(
    request: Request,
    device_id: str | None = None,
    reason: ReasonCode | None = None,
    condition: Literal["ACTIVE", "CLEARED"] | None = None,
    acknowledged: bool | None = None,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    async with request.app.state.db.sessions() as session:
        filters = []
        if device_id:
            if await session.get(Device, device_id) is None:
                raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
            filters.append(Alarm.device_id == device_id)
        if reason:
            filters.append(Alarm.reason_code == reason)
        if condition:
            filters.append(Alarm.condition == condition)
        if acknowledged is not None:
            filters.append(
                Alarm.acknowledged_at.is_not(None)
                if acknowledged
                else Alarm.acknowledged_at.is_(None)
            )
        if cursor:
            previous = await session.get(Alarm, str(cursor))
            if previous is None or device_id and previous.device_id != device_id:
                raise DomainError("INVALID_ARGUMENTS", "告警游标无效")
            filters.append(
                or_(
                    Alarm.started_at < previous.started_at,
                    and_(
                        Alarm.started_at == previous.started_at, Alarm.alarm_id < previous.alarm_id
                    ),
                )
            )
        rows = (
            await session.scalars(
                select(Alarm)
                .where(*filters)
                .order_by(Alarm.started_at.desc(), Alarm.alarm_id.desc())
                .limit(limit + 1)
            )
        ).all()
        return success(
            request,
            {
                "items": [alarm_data(row) for row in rows[:limit]],
                "next_cursor": rows[limit - 1].alarm_id if len(rows) > limit else None,
            },
        )


@router.post("/alarms/{alarm_id}/acknowledge")
async def acknowledge(request: Request, alarm_id: UUID, body: VersionedRequest):
    return success(
        request,
        await request.app.state.alarms.acknowledge(
            str(alarm_id), str(body.request_id), body.expected_version
        ),
    )


@router.get("/alarm-rules/{device_id}/{reason}")
async def rule(request: Request, device_id: str, reason: ReasonCode):
    return success(request, await request.app.state.alarms.get_rule(device_id, reason))


@router.put("/alarm-rules/{device_id}/{reason}")
async def change_rule(request: Request, device_id: str, reason: ReasonCode, body: RuleChange):
    changes = body.model_dump(exclude={"request_id", "expected_version"}, exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise DomainError("INVALID_ARGUMENTS", "规则值不能为 null")
    return success(
        request,
        await request.app.state.alarms.change_rule(
            device_id, reason, str(body.request_id), body.expected_version, changes
        ),
    )
