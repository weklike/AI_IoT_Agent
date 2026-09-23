"""Persist authoritative reports before sending an application acknowledgement."""

from datetime import datetime

from sqlalchemy import or_, select

from backend.app.charging.contracts import SessionAck, SessionReportMessage
from backend.app.db import Database
from backend.app.models import ChargingSession, DiagnosticEvent, SessionReport


async def store_report(
    db: Database, report: SessionReportMessage, received_at: datetime
) -> SessionAck:
    payload = report.model_dump(mode="json")
    status = "stored"
    async with db.sessions.begin() as session:
        charging = await session.get(ChargingSession, str(report.session_id))
        age = (received_at - report.observed_at).total_seconds()
        if charging is None or charging.device_id != report.device_id or not -5 <= age <= 86400:
            status = "rejected"
        else:
            existing = (
                await session.scalars(
                    select(SessionReport).where(
                        or_(
                            SessionReport.report_id == str(report.report_id),
                            (SessionReport.session_id == str(report.session_id))
                            & (SessionReport.report_seq == report.report_seq),
                        )
                    )
                )
            ).all()
            if existing:
                status = (
                    "stored"
                    if len(existing) == 1 and existing[0].payload_json == payload
                    else "conflict"
                )
            else:
                session.add(
                    SessionReport(
                        report_id=str(report.report_id),
                        session_id=str(report.session_id),
                        report_seq=report.report_seq,
                        payload_json=payload,
                        observed_at=report.observed_at,
                        received_at=received_at,
                    )
                )
                if report.report_seq > charging.report_seq and charging.status not in {
                    "COMPLETED",
                    "INTERRUPTED",
                }:
                    for field in (
                        "status",
                        "started_at",
                        "observed_at",
                        "ended_at",
                        "start_meter_wh",
                        "end_meter_wh",
                        "energy_wh",
                        "meter_quality",
                        "end_reason",
                        "report_seq",
                    ):
                        setattr(charging, field, getattr(report, field))
        if status != "stored":
            session.add(
                DiagnosticEvent(
                    event_type="session_report_" + status,
                    device_id=report.device_id,
                    received_at=received_at,
                    summary=f"report_id={report.report_id}; session_id={report.session_id}; seq={report.report_seq}",
                )
            )
    return SessionAck(
        report_id=report.report_id,
        session_id=report.session_id,
        report_seq=report.report_seq,
        status=status,
    )
