"""Load a full hour only into an empty, owned test database; no HTTP reset API."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import Device, Telemetry


async def main():
    if os.environ.get("APP_ENV") != "test":
        raise RuntimeError("Requires APP_ENV=test")
    settings = Settings()
    db = Database(settings)
    now = datetime.now(UTC)
    try:
        async with db.sessions.begin() as session:
            if await session.scalar(select(func.count()).select_from(Telemetry)):
                raise RuntimeError("Refusing to change a nonempty database")
            for device_id in ("CHG-001", "CHG-002", "CHG-003"):
                boot = str(uuid4())
                for seq in range(1801):
                    ts = now - timedelta(seconds=(1800 - seq) * 2)
                    row = Telemetry(
                        message_id=str(uuid4()),
                        device_id=device_id,
                        boot_id=boot,
                        seq=seq + 1,
                        schema_version=1,
                        ts=ts,
                        received_at=ts,
                        temperature_c=38,
                        voltage_v=400,
                        current_a=50,
                        power_kw=20,
                        operating_state="charging",
                    )
                    session.add(row)
                await session.flush()
                device = await session.get(Device, device_id)
                device.latest_telemetry_id = row.id
                device.last_live_received_at = now
        print(json.dumps({"anchor": now.isoformat(), "rows": 5403}))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
