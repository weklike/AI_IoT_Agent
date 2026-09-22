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
