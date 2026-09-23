"""Bounded read models; all fleet facts share one clock anchor and SQLite snapshot."""

from datetime import timedelta

from sqlalchemy import case, func, select, text

from backend.app.charging.service import charging_statistics, list_sessions
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import (
    Alarm,
    Device,
    DeviceCommand,
    PowerPlan,
    StationState,
    Telemetry,
    WorkOrder,
)
from backend.app.telemetry.queries import device_status
from backend.app.timeline import TimelineService


def fields(row, names):
    return {name: getattr(row, name) for name in names}


class ReadQueries:
    def __init__(self, db: Database, settings: Settings, clock: DataClock):
        self.db, self.settings, self.clock = db, settings, clock

    def window(self, minutes: int):
        if type(minutes) is not int or not 1 <= minutes <= 60:
            raise DomainError("INVALID_ARGUMENTS", "工具窗口必须为1—60分钟整数")
        end = self.clock.now()
        return end - timedelta(minutes=minutes), end

    async def timeline(self, device_id: str, window_minutes: int) -> dict:
        start, end = self.window(window_minutes)
        return await TimelineService(self.db).query(device_id, start, end)

    async def sessions(self, device_id: str, window_minutes: int):
        start, end = self.window(window_minutes)
        async with self.db.sessions() as session:
            await session.execute(text("BEGIN"))
            page = await list_sessions(session, device_id, start, end, limit=20)
            summary = await charging_statistics(session, device_id, start, end)
            return {
                "device_id": device_id,
                "from": start,
                "to": end,
                "items": page["items"],
                "summary": summary,
                "truncated": page["next_cursor"] is not None,
            }

    async def work_orders(self, device_id: str):
        async with self.db.sessions() as session:
            await session.execute(text("BEGIN"))
            if await session.get(Device, device_id) is None:
                raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
            unclosed = (
                await session.scalars(
                    select(WorkOrder)
                    .where(WorkOrder.device_id == device_id, WorkOrder.status != "CLOSED")
                    .order_by(WorkOrder.created_at.desc(), WorkOrder.order_id.desc())
                )
            ).all()
            closed = (
                await session.scalars(
                    select(WorkOrder)
                    .where(WorkOrder.device_id == device_id, WorkOrder.status == "CLOSED")
                    .order_by(WorkOrder.closed_at.desc(), WorkOrder.order_id.desc())
                    .limit(21)
                )
            ).all()
            count = await session.scalar(
                select(func.count())
                .select_from(WorkOrder)
                .where(WorkOrder.device_id == device_id, WorkOrder.status == "CLOSED")
            )
            names = (
                "order_id",
                "device_id",
                "reason_code",
                "status",
                "version",
                "alarm_id",
                "created_at",
                "closed_at",
            )
            return {
                "device_id": device_id,
                "unclosed": [fields(row, names) for row in unclosed],
                "closed": [fields(row, names) for row in closed[:20]],
                "closed_count": count,
                "truncated": len(closed) > 20,
            }

    async def fleet(self, window_minutes: int):
        start, end = self.window(window_minutes)
        async with self.db.sessions() as session:
            # SQLite's deferred implicit transactions do not start on SELECT; BEGIN is intentional.
            await session.execute(text("BEGIN"))
            devices = []
            for device_id in DEVICE_IDS:
                status = await device_status(session, device_id, end, self.settings)
                row = (
                    await session.execute(
                        select(
                            func.count(),
                            func.min(Telemetry.temperature_c),
                            func.max(Telemetry.temperature_c),
                            func.avg(Telemetry.temperature_c),
                            func.avg(Telemetry.power_kw),
                            func.sum(
                                case(
                                    (
                                        Telemetry.temperature_c
                                        >= self.settings.overheat_threshold_c,
                                        1,
                                    ),
                                    else_=0,
                                )
                            ),
                        ).where(
                            Telemetry.device_id == device_id,
                            Telemetry.ts >= start,
                            Telemetry.ts <= end,
                        )
                    )
                ).one()
                alarms = (
                    await session.scalars(
                        select(Alarm)
                        .where(Alarm.device_id == device_id, Alarm.condition == "ACTIVE")
                        .order_by(Alarm.alarm_id)
                    )
                ).all()
                devices.append(
                    {
                        "device_id": device_id,
                        "status": status,
                        "statistics": {
                            "from": start,
                            "to": end,
                            "sample_count": row[0],
                            "temperature_min_c": row[1],
                            "temperature_max_c": row[2],
                            "temperature_avg_c": row[3],
                            "power_avg_kw": row[4],
                            "overheat_count": row[5] or 0,
                        },
                        "active_alarms": [
                            fields(
                                alarm,
                                (
                                    "alarm_id",
                                    "reason_code",
                                    "condition",
                                    "evaluation_state",
                                    "version",
                                    "acknowledged_at",
                                    "started_at",
                                    "observed_at",
                                    "cleared_at",
                                    "peak_temperature_c",
                                ),
                            )
                            for alarm in alarms
                        ],
                        "charging_statistics": await charging_statistics(
                            session, device_id, start, end
                        ),
                    }
                )
            station = await session.get(StationState, 1)
            latest = await session.scalar(
                select(PowerPlan)
                .order_by(PowerPlan.created_at.desc(), PowerPlan.plan_id.desc())
                .limit(1)
            )
            plan = None
            if latest:
                plan = fields(
                    latest,
                    (
                        "plan_id",
                        "strategy",
                        "status",
                        "budget_w",
                        "created_at",
                        "finished_at",
                        "allocation_json",
                        "results_json",
                    ),
                )
                plan["device_priority"] = latest.snapshot_json.get("device_priority")
                confirmations = {}
                for device_id in DEVICE_IDS:
                    item = latest.results_json.get(device_id, {})
                    command_id = item.get("command_id") if isinstance(item, dict) else None
                    command = await session.get(DeviceCommand, command_id) if command_id else None
                    confirmations[device_id] = (
                        fields(
                            command, ("command_id", "status", "verification_status", "error_code")
                        )
                        if command
                        else None
                    )
                plan["confirmations"] = confirmations
            return {
                "from": start,
                "to": end,
                "window_minutes": window_minutes,
                "devices": devices,
                "station": fields(station, ("budget_w", "revision", "executing_plan_id")),
                "latest_plan": plan,
            }
