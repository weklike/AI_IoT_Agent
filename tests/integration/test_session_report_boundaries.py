"""Report identity, ordering and invalid facts cannot alter authoritative sessions."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.charging.contracts import SessionReportMessage
from backend.app.charging.reports import store_report
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import ChargingSession, SessionReport
from tests.support.clock import FixedClock


def report(now, registered_session_id, **changes):
    return {
        "report_id": str(uuid4()),
        "session_id": registered_session_id,
        "device_id": "CHG-001",
        "report_seq": 2,
        "started_at": now - timedelta(seconds=600),
        "observed_at": now,
        "ended_at": None,
        "status": "ACTIVE",
        "start_meter_wh": 10000,
        "end_meter_wh": 13333,
        "energy_wh": 3333,
        "end_reason": None,
        "meter_quality": "exact",
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"energy_wh": 3334},
        {"end_meter_wh": 9999, "energy_wh": 0},
        {"start_meter_wh": -1},
        {"report_seq": True},
        {"report_seq": "2"},
        {"report_seq": 0},
        {"energy_wh": float("nan")},
        {"extra": "not permitted"},
        {"status": "COMPLETED"},
        {"end_reason": "USER_STOP"},
        {"session_id": "invalid"},
    ],
)
def test_invalid_report_facts_are_rejected(fixed_now, changes):
    with pytest.raises(ValidationError):
        SessionReportMessage.model_validate(report(fixed_now, str(uuid4()), **changes))


async def test_report_seq_conflict_ordering_device_and_age_preserve_original(tmp_path, fixed_now):
    db = Database(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/reports.db",
        )
    )
    await db.initialize(FixedClock(fixed_now))
    sid = str(uuid4())
    try:
        async with db.sessions.begin() as session:
            session.add(
                ChargingSession(
                    session_id=sid, device_id="CHG-001", status="ACTIVE", requested_power_w=20000
                )
            )

        async def send(payload, received_at=fixed_now):
            return await store_report(db, SessionReportMessage.model_validate(payload), received_at)

        original = report(fixed_now, sid)
        assert (await send(original)).status == "stored"
        assert (await send(original, fixed_now + timedelta(seconds=1))).status == "stored"
        assert (await send({**original, "report_id": str(uuid4())})).status == "conflict"
        assert (await send(report(fixed_now, sid, device_id="CHG-002"))).status == "rejected"
        assert (await send(report(fixed_now, str(uuid4())))).status == "rejected"
        assert (
            await send(report(fixed_now, sid, report_seq=3), fixed_now + timedelta(seconds=86401))
        ).status == "rejected"
        assert (
            await send(report(fixed_now, sid, report_seq=3), fixed_now - timedelta(seconds=6))
        ).status == "rejected"
        older = report(
            fixed_now - timedelta(seconds=10), sid, report_seq=1, end_meter_wh=13000, energy_wh=3000
        )
        assert (await send(older)).status == "stored"
        async with db.sessions() as session:
            current = await session.get(ChargingSession, sid)
            assert (current.report_seq, current.energy_wh, current.end_meter_wh) == (2, 3333, 13333)
            assert await session.scalar(select(func.count()).select_from(SessionReport)) == 2
            saved = await session.get(SessionReport, original["report_id"])
            assert saved.payload_json == SessionReportMessage.model_validate(original).model_dump(
                mode="json"
            )
    finally:
        await db.close()
