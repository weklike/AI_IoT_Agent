"""Read-only event projection. Paging never changes the clock, live state or source records."""

from datetime import datetime

from sqlalchemy import JSON, func, literal, or_, select, text, type_coerce, union_all

from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import (
    AlarmEvent,
    ChargingSession,
    Device,
    DeviceCommand,
    ScenarioCommandRow,
    SessionReport,
    ToolCall,
    WorkOrder,
    WorkOrderEvent,
)


def event(kind, identity, observed, received, payload):
    return select(
        literal(kind).label("source_type"),
        identity.label("source_id"),
        observed.label("observed_at"),
        received.label("received_at"),
        type_coerce(payload, JSON).label("detail"),
    )


def obj(**values):
    return func.json_object(*[part for key, value in values.items() for part in (key, value)])


class TimelineService:
    def __init__(self, db: Database):
        self.db = db

    async def query(
        self, device_id: str, start: datetime, end: datetime, *, limit: int = 100
    ) -> dict:
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or start > end
            or (end - start).total_seconds() > 86400
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise DomainError(
                "INVALID_ARGUMENTS", "时间线窗口必须正序、带时区、最多24小时；最多100条"
            )
        commands = event(
            "device_command",
            DeviceCommand.command_id,
            DeviceCommand.issued_at,
            DeviceCommand.issued_at,
            obj(
                action=DeviceCommand.action,
                generation=DeviceCommand.generation,
                status=DeviceCommand.status,
                verification_status=DeviceCommand.verification_status,
            ),
        ).where(DeviceCommand.device_id == device_id)
        ack = event(
            "device_ack",
            DeviceCommand.command_id,
            func.coalesce(DeviceCommand.ack_observed_at, DeviceCommand.ack_at),
            DeviceCommand.ack_at,
            obj(
                ack=DeviceCommand.ack_json,
                observed_time_known=DeviceCommand.ack_observed_at.is_not(None),
            ),
        ).where(DeviceCommand.device_id == device_id, DeviceCommand.ack_at.is_not(None))
        late_ack = event(
            "device_late_ack",
            DeviceCommand.command_id,
            DeviceCommand.late_ack_observed_at,
            DeviceCommand.late_ack_received_at,
            DeviceCommand.late_ack_json,
        ).where(DeviceCommand.device_id == device_id)
        scenario = event(
            "scenario_command",
            ScenarioCommandRow.command_id,
            ScenarioCommandRow.requested_at,
            ScenarioCommandRow.requested_at,
            obj(scenario=ScenarioCommandRow.scenario, status=ScenarioCommandRow.status),
        ).where(ScenarioCommandRow.device_id == device_id)
        scenario_ack = event(
            "scenario_ack",
            ScenarioCommandRow.command_id,
            ScenarioCommandRow.ack_at,
            ScenarioCommandRow.ack_received_at,
            obj(status=ScenarioCommandRow.status),
        ).where(ScenarioCommandRow.device_id == device_id, ScenarioCommandRow.ack_at.is_not(None))
        scenario_late = event(
            "scenario_late_ack",
            ScenarioCommandRow.command_id,
            ScenarioCommandRow.late_ack_observed_at,
            ScenarioCommandRow.late_ack_received_at,
            ScenarioCommandRow.late_ack_json,
        ).where(ScenarioCommandRow.device_id == device_id)
        reports = (
            event(
                "session_report",
                SessionReport.report_id,
                SessionReport.observed_at,
                SessionReport.received_at,
                SessionReport.payload_json,
            )
            .join(ChargingSession, ChargingSession.session_id == SessionReport.session_id)
            .where(ChargingSession.device_id == device_id)
        )
        alarms = event(
            "alarm_event",
            AlarmEvent.event_id,
            AlarmEvent.observed_at,
            AlarmEvent.received_at,
            obj(
                alarm_id=AlarmEvent.alarm_id,
                event_type=AlarmEvent.event_type,
                evidence=AlarmEvent.evidence_json,
            ),
        ).where(AlarmEvent.device_id == device_id)
        orders = (
            event(
                "work_order_event",
                WorkOrderEvent.event_id,
                WorkOrderEvent.checked_at,
                WorkOrderEvent.checked_at,
                obj(
                    order_id=WorkOrderEvent.order_id,
                    from_status=WorkOrderEvent.from_status,
                    to_status=WorkOrderEvent.to_status,
                    note=WorkOrderEvent.note,
                    evidence=WorkOrderEvent.evidence_json,
                ),
            )
            .join(WorkOrder, WorkOrder.order_id == WorkOrderEvent.order_id)
            .where(WorkOrder.device_id == device_id)
        )
        created = event(
            "work_order_created",
            WorkOrder.order_id,
            WorkOrder.created_at,
            WorkOrder.created_at,
            obj(
                reason_code=WorkOrder.reason_code, created_from_run_id=WorkOrder.created_from_run_id
            ),
        ).where(WorkOrder.device_id == device_id)
        tools = event(
            "tool_call",
            ToolCall.tool_call_id,
            ToolCall.started_at,
            ToolCall.started_at,
            obj(
                event_phase=literal("started"),
                run_id=ToolCall.run_id,
                tool_name=ToolCall.tool_name,
                status=ToolCall.status,
                duration_ms=ToolCall.duration_ms,
                error_code=ToolCall.error_code,
            ),
        ).where(
            or_(
                ToolCall.args_json["device_id"].as_string() == device_id,
                ToolCall.tool_name == "get_fleet_overview",
            )
        )
        all_events = union_all(
            commands,
            ack,
            late_ack,
            scenario,
            scenario_ack,
            scenario_late,
            reports,
            alarms,
            orders,
            created,
            tools,
        ).subquery()
        filters = [all_events.c.observed_at >= start, all_events.c.observed_at <= end]
        async with self.db.sessions() as session:
            await session.execute(text("BEGIN"))
            if await session.get(Device, device_id) is None:
                raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
            counts = (
                await session.execute(
                    select(all_events.c.source_type, func.count())
                    .where(*filters)
                    .group_by(all_events.c.source_type)
                )
            ).all()
            rows = (
                (
                    await session.execute(
                        select(all_events)
                        .where(*filters)
                        .order_by(
                            all_events.c.observed_at.desc(),
                            all_events.c.source_type.desc(),
                            all_events.c.source_id.desc(),
                        )
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
            items = []
            for row in reversed(rows):
                item = dict(row) | {"device_id": device_id}
                item["late_received"] = (
                    (item["received_at"] > item["observed_at"]) if item["received_at"] else None
                )
                items.append(item)
            count = sum(value for _, value in counts)
            return {
                "device_id": device_id,
                "from": start,
                "to": end,
                "event_count": count,
                "counts_by_source": dict(counts),
                "items": items,
                "truncated": count > limit,
            }
