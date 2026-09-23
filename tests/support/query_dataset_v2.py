"""Owned empty performance DB only: 5403 v2 samples, 90 sessions, 120 mixed events."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, insert, select

from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import (
    AgentRun,
    Alarm,
    AlarmEvent,
    ChargingSession,
    Device,
    KnowledgeDocument,
    OperationRequest,
    Telemetry,
    WorkOrder,
    WorkOrderEvent,
)


def uid(name):
    return str(uuid5(NAMESPACE_URL, "performance-v2/" + name))


async def seed(db, now):
    async with db.sessions.begin() as session:
        for model in (Telemetry, ChargingSession, Alarm, AlarmEvent, WorkOrder, WorkOrderEvent):
            if await session.scalar(select(func.count()).select_from(model)):
                raise RuntimeError("Refusing to change nonempty performance tables")
        for d in range(1, 4):
            device = f"CHG-{d:03}"
            sessions = []
            for i in range(30):
                started = now - timedelta(seconds=3600 - i * 120)
                end = started + timedelta(seconds=120)
                start_meter = 10000 + (i * 20000) // 30
                end_meter = 10000 + ((i + 1) * 20000) // 30
                sessions.append(
                    dict(
                        session_id=uid(f"{device}/session/{i}"),
                        device_id=device,
                        status="ACTIVE" if i == 29 else "COMPLETED",
                        requested_power_w=20000,
                        started_at=started,
                        observed_at=end,
                        ended_at=None if i == 29 else end,
                        start_meter_wh=start_meter,
                        end_meter_wh=end_meter,
                        energy_wh=end_meter - start_meter,
                        meter_quality="exact",
                        end_reason=None if i == 29 else "USER_STOP",
                        report_seq=2,
                    )
                )
            await session.execute(insert(ChargingSession), sessions)
            samples = []
            for seq in range(1801):
                ts = now - timedelta(seconds=(1800 - seq) * 2)
                index = min(seq // 60, 29)
                meter = 10000 + (seq * 20000) // 1800
                start_meter = 10000 + (index * 20000) // 30
                samples.append(
                    dict(
                        message_id=uid(f"{device}/sample/{seq}"),
                        device_id=device,
                        boot_id=uid(device + "/boot"),
                        seq=seq + 1,
                        schema_version=2,
                        ts=ts,
                        received_at=ts,
                        temperature_c=38.0,
                        voltage_v=400.0,
                        current_a=50.0,
                        power_kw=20.0,
                        operating_state="charging",
                        session_id=uid(f"{device}/session/{index}"),
                        session_state="ACTIVE",
                        requested_power_w=20000,
                        power_limit_w=20000,
                        meter_total_wh=meter,
                        session_energy_wh=meter - start_meter,
                        applied_control_generation=index * 2 + 2,
                    )
                )
            await session.execute(insert(Telemetry), samples)
            row = await session.scalar(
                select(Telemetry)
                .where(Telemetry.device_id == device)
                .order_by(Telemetry.seq.desc())
                .limit(1)
            )
            device_row = await session.get(Device, device)
            device_row.latest_telemetry_id = row.id
            device_row.last_live_received_at = now
        session.add(
            AgentRun(
                run_id=uid("fixture-run"),
                request_id=uid("fixture-request"),
                request_hash="fixture",
                question="性能夹具，不是模型执行",
                status="completed",
                created_at=now - timedelta(hours=1),
            )
        )
        await session.flush()
        for i in range(30):
            device = f"CHG-{i % 3 + 1:03}"
            at = now - timedelta(seconds=3500 - i * 100)
            alarm_id = uid(f"alarm/{i}")
            session.add(
                Alarm(
                    alarm_id=alarm_id,
                    device_id=device,
                    reason_code="OVERHEAT",
                    condition="CLEARED",
                    version=2,
                    evaluation_state="known",
                    peak_temperature_c=72.0,
                    started_at=at,
                    observed_at=at + timedelta(seconds=20),
                    cleared_at=at + timedelta(seconds=20),
                    rule_json={"fixture": True},
                    evidence_json={"fixture": True},
                )
            )
            await session.flush()
            for event, offset in (("RAISED", 0), ("CLEARED", 20)):
                session.add(
                    AlarmEvent(
                        event_id=uid(f"alarm/{i}/{event}"),
                        alarm_id=alarm_id,
                        device_id=device,
                        event_type=event,
                        observed_at=at + timedelta(seconds=offset),
                        received_at=at + timedelta(seconds=offset),
                        evidence_json={"fixture": True},
                    )
                )
            if i < 20:
                order = uid(f"order/{i}")
                session.add(
                    WorkOrder(
                        order_id=order,
                        device_id=device,
                        reason_code="OVERHEAT",
                        status="CLOSED",
                        version=4,
                        alarm_id=alarm_id,
                        evidence_json={"fixture": True},
                        created_from_run_id=uid("fixture-run"),
                        created_at=at,
                        closed_at=at + timedelta(seconds=30),
                    )
                )
                await session.flush()
                for step, (old, new) in enumerate(
                    (("OPEN", "IN_PROGRESS"), ("IN_PROGRESS", "RESOLVED"), ("RESOLVED", "CLOSED")),
                    1,
                ):
                    request = uid(f"order/{i}/request/{step}")
                    checked = at + timedelta(seconds=step * 10)
                    session.add(
                        OperationRequest(
                            request_id=request,
                            request_hash="fixture",
                            route=f"/work-orders/{order}/transitions",
                            action="transition",
                            result_json={"fixture": True},
                            created_at=checked,
                        )
                    )
                    await session.flush()
                    session.add(
                        WorkOrderEvent(
                            event_id=uid(f"order/{i}/event/{step}"),
                            order_id=order,
                            request_id=request,
                            from_status=old,
                            to_status=new,
                            note="性能合成前置记录",
                            checked_at=checked,
                            evidence_json={"fixture": True},
                        )
                    )
    async with db.sessions() as session:
        counts = {
            model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in (Telemetry, ChargingSession, AlarmEvent, WorkOrderEvent, KnowledgeDocument)
        }
    return {
        "anchor": now.isoformat(),
        "counts": counts,
        "source": "synthetic performance fixture; not model output",
    }


async def main():
    if os.environ.get("APP_ENV") != "test":
        raise RuntimeError("Requires APP_ENV=test in an owned test container")
    db = Database(Settings())
    try:
        print(json.dumps(await seed(db, datetime.now(UTC))))
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
