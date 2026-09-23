"""Session queries aggregate the complete window; pagination only limits display rows."""

import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.errors import DomainError
from backend.app.models import ChargingSession, Device, DeviceCommand


def session_data(row: ChargingSession) -> dict:
    result = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    end = row.ended_at or row.observed_at
    result["duration_seconds"] = (
        (end - row.started_at).total_seconds() if end and row.started_at else None
    )
    result["report_missing"] = row.observed_at is None
    return result


def _effective_start():
    issued = (
        select(func.min(DeviceCommand.issued_at))
        .where(
            DeviceCommand.action == "start_session",
            DeviceCommand.args_json["session_id"].as_string() == ChargingSession.session_id,
        )
        .correlate(ChargingSession)
        .scalar_subquery()
    )
    return func.coalesce(ChargingSession.started_at, issued, ChargingSession.observed_at)


async def _window(session: AsyncSession, device_id: str, start: datetime, end: datetime):
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start > end
        or (end - start).total_seconds() > 86400
    ):
        raise DomainError("INVALID_ARGUMENTS", "会话窗口必须带时区、正序且最多 24 小时")
    if await session.get(Device, device_id) is None:
        raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
    effective = _effective_start()
    return [
        ChargingSession.device_id == device_id,
        effective <= end,
        or_(ChargingSession.ended_at.is_(None), ChargingSession.ended_at >= start),
    ]


async def list_sessions(
    session: AsyncSession,
    device_id: str,
    start: datetime,
    end: datetime,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise DomainError("INVALID_ARGUMENTS", "分页数量必须为 1—100")
    filters = await _window(session, device_id, start, end)
    effective = _effective_start()
    scope = hashlib.sha256(
        f"{device_id}|{start.isoformat()}|{end.isoformat()}".encode()
    ).hexdigest()
    if cursor:
        try:
            if len(cursor) > 2048:
                raise ValueError("Cursor too long")
            content = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if set(content) != {"scope", "at", "id"} or content["scope"] != scope:
                raise ValueError("Cursor belongs to another window")
            at = datetime.fromisoformat(content["at"])
            if at.tzinfo is None:
                raise ValueError("Cursor must have timezone")
            identity = str(UUID(content["id"]))
        except (ValueError, TypeError, KeyError) as error:
            raise DomainError("INVALID_ARGUMENTS", "分页游标无效") from error
        filters.append(
            or_(effective < at, and_(effective == at, ChargingSession.session_id < identity))
        )
    rows = (
        await session.execute(
            select(ChargingSession, effective.label("effective_start"))
            .where(*filters)
            .order_by(effective.desc(), ChargingSession.session_id.desc())
            .limit(limit + 1)
        )
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if more:
        row, at = rows[-1]
        next_cursor = base64.urlsafe_b64encode(
            json.dumps({"scope": scope, "at": at.isoformat(), "id": row.session_id}).encode()
        ).decode()
    return {"items": [session_data(row) for row, _ in rows], "next_cursor": next_cursor}


async def charging_statistics(
    session: AsyncSession, device_id: str, start: datetime, end: datetime
) -> dict:
    filters = await _window(session, device_id, start, end)
    ended = and_(
        ChargingSession.status.in_(["COMPLETED", "INTERRUPTED"]),
        ChargingSession.ended_at >= start,
        ChargingSession.ended_at <= end,
    )
    row = (
        await session.execute(
            select(
                func.count(ChargingSession.session_id),
                func.sum(case((ChargingSession.status == "ACTIVE", 1), else_=0)),
                func.sum(case((ChargingSession.report_seq == 0, 1), else_=0)),
                func.sum(case((ended, ChargingSession.energy_wh), else_=None)),
                func.sum(case((ended, 1), else_=0)),
            ).where(*filters)
        )
    ).one()
    return {
        "device_id": device_id,
        "from": start,
        "to": end,
        "session_count": row[0],
        "active_count": row[1] or 0,
        "missing_report_count": row[2] or 0,
        "completed_session_energy_wh": row[3],
        "ended_session_count": row[4] or 0,
    }


async def get_session(session: AsyncSession, session_id: str) -> dict:
    row = await session.get(ChargingSession, session_id)
    if row is None:
        raise DomainError("SESSION_NOT_FOUND", "会话不存在", 404)
    return session_data(row)
