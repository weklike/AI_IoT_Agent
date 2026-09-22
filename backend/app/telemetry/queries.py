from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings
from backend.app.errors import DomainError
from backend.app.models import Device, Telemetry


async def device_status(
    session: AsyncSession, device_id: str, now: datetime, settings: Settings
) -> dict:
    device = await session.get(Device, device_id)
    if device is None:
        raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
    sample = (
        await session.get(Telemetry, device.latest_telemetry_id)
        if device.latest_telemetry_id
        else None
    )
    age = max(0.0, (now - sample.ts).total_seconds()) if sample else None
    live = device.last_live_received_at
    connection = (
        "unknown"
        if live is None
        else (
            "online"
            if (now - live).total_seconds() <= settings.offline_timeout_seconds
            else "offline"
        )
    )
    fresh = live is not None and age is not None and age <= settings.fresh_sample_max_age_seconds
    health = (
        ("overheat" if sample.temperature_c >= settings.overheat_threshold_c else "normal")
        if fresh
        else "unknown"
    )
    return {
        "device_id": device_id,
        "name": device.name,
        "connection_state": connection,
        "health_state": health,
        "data_fresh": fresh,
        "data_age_seconds": age,
        "sample_ts": sample.ts if sample else None,
        "message_id": sample.message_id if sample else None,
        "temperature_c": sample.temperature_c if sample else None,
        "voltage_v": sample.voltage_v if sample else None,
        "current_a": sample.current_a if sample else None,
        "power_kw": sample.power_kw if sample else None,
        "operating_state": sample.operating_state if sample else None,
        "last_live_received_at": live,
    }


async def history_rows(
    session: AsyncSession, device_id: str, start: datetime, end: datetime
) -> list[Telemetry]:
    from sqlalchemy import select

    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start > end
        or (end - start).total_seconds() > 86400
    ):
        raise DomainError("INVALID_ARGUMENTS", "历史区间必须带时区、正序且不超过 24 小时")
    if await session.get(Device, device_id) is None:
        raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
    rows = list(
        (
            await session.scalars(
                select(Telemetry)
                .where(
                    Telemetry.device_id == device_id,
                    Telemetry.ts >= start,
                    Telemetry.ts <= end,
                )
                .order_by(Telemetry.ts, Telemetry.id)
                .limit(5001)
            )
        ).all()
    )
    if len(rows) > 5000:
        raise DomainError("HISTORY_LIMIT_EXCEEDED", "历史超过 5000 行，请缩小时间区间")
    return rows


def sample_dict(row: Telemetry) -> dict:
    return {
        "message_id": row.message_id,
        "device_id": row.device_id,
        "sample_ts": row.ts,
        "temperature_c": row.temperature_c,
        "voltage_v": row.voltage_v,
        "current_a": row.current_a,
        "power_kw": row.power_kw,
        "operating_state": row.operating_state,
    }


def summarize(rows: list[Telemetry], start: datetime, end: datetime, threshold: float) -> dict:
    if not rows:
        raise DomainError("NO_DATA", "该时间区间没有样本")
    temperatures = [row.temperature_c for row in rows]
    hot = [row for row in rows if row.temperature_c >= threshold]
    intervals: list[dict] = []
    current = None
    for row in rows:
        if row.temperature_c >= threshold:
            if current is None:
                current = {"from": row.ts, "to": row.ts, "sample_count": 0}
                intervals.append(current)
            current["to"] = row.ts
            current["sample_count"] += 1
        else:
            current = None
    # Endpoint-preserving display sample; all original rows are used above for statistics.
    indices = (
        sorted({round(i * (len(rows) - 1) / 99) for i in range(100)})
        if len(rows) > 100
        else range(len(rows))
    )
    return {
        "device_id": rows[0].device_id,
        "from": start,
        "to": end,
        "sample_count": len(rows),
        "temperature_min_c": min(temperatures),
        "temperature_max_c": max(temperatures),
        "temperature_avg_c": round(sum(temperatures) / len(rows), 2),
        "overheat_count": len(hot),
        "overheat_intervals": intervals,
        "overheat_samples": [{"message_id": row.message_id, "sample_ts": row.ts} for row in hot],
        "samples": [sample_dict(rows[i]) for i in indices],
    }
