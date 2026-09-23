import logging
from datetime import datetime

from sqlalchemy import and_, or_, select

from backend.app.alarms.service import AlarmService
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import TelemetryMessage, TelemetryV2, parse_telemetry
from backend.app.db import Database
from backend.app.models import Device, DiagnosticEvent, Telemetry
from backend.app.telemetry.queries import device_status

logger = logging.getLogger(__name__)


class TelemetryStore:
    def __init__(self, db: Database, settings: Settings, clock: DataClock):
        self.db, self.settings, self.clock = db, settings, clock
        self.alarms = AlarmService(db, settings, clock)

    async def diagnostic(
        self, event_type: str, device_id: str | None, summary: str, received_at: datetime
    ) -> None:
        async with self.db.sessions.begin() as session:
            session.add(
                DiagnosticEvent(
                    event_type=event_type,
                    device_id=device_id,
                    summary=summary,
                    received_at=received_at,
                )
            )

    async def receive(
        self, payload: bytes, topic: str, received_at: datetime, retained: bool
    ) -> str:
        if retained:
            await self.diagnostic("retained", None, "Retained telemetry ignored", received_at)
            return "rejected"
        try:
            message = parse_telemetry(payload, topic, received_at, self.settings.mqtt_topic_prefix)
        except ValueError:
            # Do not persist arbitrary payloads or validation errors containing input values.
            await self.diagnostic(
                "rejected", None, "Invalid telemetry payload/topic/time", received_at
            )
            return "rejected"
        return await self.ingest(message, received_at)

    async def ingest(
        self, message: TelemetryMessage | TelemetryV2, received_at: datetime, retained: bool = False
    ) -> str:
        if retained:
            await self.diagnostic(
                "retained", message.device_id, "Retained telemetry ignored", received_at
            )
            return "rejected"
        # Internal callers cannot bypass the same time and schema checks used by MQTT.
        message = parse_telemetry(
            message.model_dump_json().encode(),
            f"{self.settings.mqtt_topic_prefix}/devices/{message.device_id}/telemetry",
            received_at,
            self.settings.mqtt_topic_prefix,
        )
        fields = message.model_dump(mode="python")
        fields["message_id"], fields["boot_id"] = str(message.message_id), str(message.boot_id)
        if isinstance(message, TelemetryV2):
            fields["session_id"] = str(message.session_id) if message.session_id else None
        async with self.db.sessions.begin() as session:
            existing = (
                await session.scalars(
                    select(Telemetry).where(
                        or_(
                            Telemetry.message_id == fields["message_id"],
                            and_(
                                Telemetry.device_id == message.device_id,
                                Telemetry.boot_id == fields["boot_id"],
                                Telemetry.seq == message.seq,
                            ),
                        )
                    )
                )
            ).all()
            if existing:
                identical = len(existing) == 1 and all(
                    getattr(existing[0], key) == value for key, value in fields.items()
                )
                result = "duplicate" if identical else "conflict"
                session.add(
                    DiagnosticEvent(
                        event_type=result,
                        device_id=message.device_id,
                        received_at=received_at,
                        summary="Existing unique telemetry key: " + result,
                    )
                )
                return result
            device = await session.get(Device, message.device_id)
            row = Telemetry(**fields, received_at=received_at)
            session.add(row)
            await session.flush()
            current = (
                await session.get(Telemetry, device.latest_telemetry_id)
                if device.latest_telemetry_id
                else None
            )
            if current is None or message.ts > current.ts:
                device.latest_telemetry_id = row.id
                if (
                    received_at - message.ts
                ).total_seconds() <= self.settings.fresh_sample_max_age_seconds:
                    device.last_live_received_at = received_at
                    await self.alarms.observe(session, row, received_at)
                else:
                    await self.alarms.interrupt(session, message.device_id)
            else:
                await self.alarms.interrupt(session, message.device_id)
        # Logged strictly after commit; usable for later performance correlation.
        logger.info(
            "telemetry_committed message_id=%s device_id=%s committed_at=%s",
            message.message_id,
            message.device_id,
            self.clock.now().isoformat(),
        )
        return "accepted"

    async def device_status(self, device_id: str) -> dict:
        async with self.db.sessions() as session:
            return await device_status(session, device_id, self.clock.now(), self.settings)

    async def history(self, device_id: str, window_minutes: int) -> dict:
        from datetime import timedelta

        from backend.app.errors import DomainError
        from backend.app.telemetry.queries import history_rows, summarize

        if type(window_minutes) is not int or not 1 <= window_minutes <= 60:
            raise DomainError("INVALID_ARGUMENTS", "历史工具窗口必须为 1—60 分钟整数")
        end = self.clock.now()
        start = end - timedelta(minutes=window_minutes)
        async with self.db.sessions() as session:
            rows = await history_rows(session, device_id, start, end)
            return summarize(rows, start, end, self.settings.overheat_threshold_c)
