from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

from backend.app.api import json_data
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import ToolContext
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import AgentRun, Alarm, Telemetry, ToolCall, WorkOrder, WorkOrderEvent
from backend.app.operations import execute_operation
from backend.app.telemetry.queries import device_status


class WorkOrderService:
    def __init__(self, db: Database, settings: Settings, clock: DataClock):
        self.db, self.settings, self.clock = db, settings, clock

    async def _evidence(
        self, session, device_id: str, reason_code: str, run_id: str, now: datetime
    ) -> dict:
        reads = (
            await session.scalars(
                select(ToolCall)
                .where(
                    ToolCall.run_id == run_id,
                    ToolCall.status == "succeeded",
                    ToolCall.tool_name.in_(["get_device_status", "get_device_history"]),
                )
                .order_by(ToolCall.started_at.desc())
            )
        ).all()
        for read in reads:
            result = read.result_json or {}
            data = result.get("data") or {}
            if (
                read.args_json.get("device_id") != device_id
                or data.get("device_id") != device_id
                or result.get("ok") is not True
            ):
                continue
            ids = []
            if reason_code == "OFFLINE":
                if (
                    read.tool_name != "get_device_status"
                    or data.get("connection_state") != "offline"
                ):
                    continue
                current = await device_status(session, device_id, now, self.settings)
                if current["connection_state"] != "offline":
                    continue
                ids = [data.get("message_id")]
            elif read.tool_name == "get_device_status":
                if data.get("health_state") != "overheat" or data.get("data_fresh") is not True:
                    continue
                ids = [data.get("message_id")]
            elif read.tool_name == "get_device_history":
                ids = [item.get("message_id") for item in data.get("overheat_samples", [])]
            if not ids:
                continue
            originals = (
                await session.scalars(
                    select(Telemetry).where(
                        Telemetry.message_id.in_(ids),
                        Telemetry.device_id == device_id,
                    )
                )
            ).all()
            selected = []
            for sample in originals:
                age = max(0, (now - sample.ts).total_seconds())
                if reason_code == "OVERHEAT":
                    max_age = (
                        self.settings.fresh_sample_max_age_seconds
                        if read.tool_name == "get_device_status"
                        else 3600
                    )
                    if sample.temperature_c < self.settings.overheat_threshold_c or age > max_age:
                        continue
                selected.append(
                    {
                        "message_id": sample.message_id,
                        "sample_ts": sample.ts,
                        "temperature_c": sample.temperature_c,
                    }
                )
            if selected:
                return json_data(
                    {
                        "tool_call_id": read.tool_call_id,
                        "samples": selected,
                        "validated_at": now,
                        "run_id": run_id,
                        "device_id": device_id,
                    }
                )
        raise DomainError("INVALID_EVIDENCE", "本次任务没有该设备的有效异常证据")

    async def create(self, device_id: str, reason_code: str, *, context: ToolContext) -> dict:
        if not context.allow_work_order:
            raise DomainError("WRITE_NOT_ALLOWED", "本次任务未授权创建工单", 403)
        if reason_code not in {"OVERHEAT", "OFFLINE"}:
            raise DomainError("INVALID_ARGUMENTS", "未知工单原因")
        try:
            async with self.db.sessions() as session:
                # Acquire SQLite's write reservation before reading evidence or the OPEN index.
                # No model/network await occurs while holding this short transaction.
                await session.execute(text("BEGIN IMMEDIATE"))
                try:
                    run = await session.get(AgentRun, str(context.run_id))
                    call = await session.get(ToolCall, str(context.tool_call_id))
                    if run is None or not run.allow_work_order:
                        raise DomainError("WRITE_NOT_ALLOWED", "本次任务未授权创建工单", 403)
                    if (
                        call is None
                        or call.run_id != run.run_id
                        or call.tool_name != "create_work_order"
                        or call.args_json != {"device_id": device_id, "reason_code": reason_code}
                    ):
                        raise DomainError("INVALID_EVIDENCE", "当前工具调用与工单请求不匹配")
                    if call.result_json is not None:
                        return call.result_json
                    now = self.clock.now()
                    evidence = await self._evidence(
                        session, device_id, reason_code, run.run_id, now
                    )
                    existing = await session.scalar(
                        select(WorkOrder).where(
                            WorkOrder.device_id == device_id,
                            WorkOrder.reason_code == reason_code,
                            WorkOrder.status.in_(["OPEN", "IN_PROGRESS", "RESOLVED"]),
                        )
                    )
                    created = existing is None
                    if existing is None:
                        alarm = await session.scalar(
                            select(Alarm).where(
                                Alarm.device_id == device_id,
                                Alarm.reason_code == reason_code,
                                Alarm.condition == "ACTIVE",
                            )
                        )
                        existing = WorkOrder(
                            order_id=str(uuid4()),
                            device_id=device_id,
                            reason_code=reason_code,
                            status="OPEN",
                            alarm_id=alarm.alarm_id if alarm else None,
                            evidence_json=evidence,
                            created_from_run_id=run.run_id,
                            created_at=now,
                        )
                        session.add(existing)
                    result = {
                        "tool_call_id": call.tool_call_id,
                        "ok": True,
                        "data": {
                            "order_id": existing.order_id,
                            "created": created,
                            "status": existing.status,
                            "evidence": evidence,
                            "device_id": device_id,
                            "reason_code": reason_code,
                        },
                        "error": None,
                    }
                    call.result_json = result
                    call.status = "succeeded"
                    await session.commit()
                    return result
                except BaseException:
                    await session.rollback()
                    raise
        except OperationalError as exc:
            raise DomainError("DATABASE_BUSY", "数据库写入暂不可用", 503) from exc

    async def transition(
        self, order_id: str, request_id: str, expected_version: int, target_status: str, note: str
    ) -> dict:
        async def apply(session) -> dict:
            order = await session.get(WorkOrder, order_id)
            if order is None:
                raise DomainError("WORK_ORDER_NOT_FOUND", "工单不存在", 404)
            if order.version != expected_version:
                raise DomainError("VERSION_CONFLICT", "工单版本已变化", 409)
            allowed = {
                "OPEN": {"IN_PROGRESS"},
                "IN_PROGRESS": {"RESOLVED"},
                "RESOLVED": {"IN_PROGRESS", "CLOSED"},
                "CLOSED": set(),
            }
            if target_status not in allowed[order.status]:
                raise DomainError("INVALID_TRANSITION", "不允许此工单状态迁移", 409)
            if (
                not isinstance(note, str)
                or len(note) > 2000
                or target_status == "RESOLVED"
                and not note.strip()
            ):
                raise DomainError("INVALID_ARGUMENTS", "待验证工单必须提供1—2000字处理说明")
            evidence = {}
            checked_at = self.clock.now()
            if target_status == "CLOSED":
                current = await device_status(session, order.device_id, checked_at, self.settings)
                recovered = current["data_fresh"] and current["connection_state"] == "online"
                if order.reason_code == "OVERHEAT":
                    recovered = (
                        recovered and current["temperature_c"] < self.settings.overheat_threshold_c
                    )
                if order.alarm_id:
                    alarm = await session.get(Alarm, order.alarm_id)
                    recovered = (
                        recovered
                        and alarm is not None
                        and alarm.condition == "CLEARED"
                        and alarm.device_id == order.device_id
                        and alarm.reason_code == order.reason_code
                    )
                if not recovered:
                    raise DomainError(
                        "RECOVERY_NOT_CONFIRMED", "需要新鲜恢复证据，且关联告警已经恢复", 409
                    )
                sample = await session.scalar(
                    select(Telemetry).where(
                        Telemetry.message_id == current["message_id"],
                        Telemetry.device_id == order.device_id,
                    )
                )
                if sample is None:
                    raise DomainError("RECOVERY_NOT_CONFIRMED", "恢复样本不可用", 409)
                evidence = json_data(
                    {
                        "device_id": order.device_id,
                        "sample_id": sample.id,
                        "message_id": sample.message_id,
                        "sample_ts": sample.ts,
                        "validated_at": checked_at,
                        "temperature_c": sample.temperature_c,
                        "connection_state": current["connection_state"],
                        "alarm_id": order.alarm_id,
                    }
                )
                order.closed_at = checked_at
            previous = order.status
            order.status = target_status
            order.version += 1
            session.add(
                WorkOrderEvent(
                    event_id=str(uuid4()),
                    order_id=order_id,
                    request_id=request_id,
                    from_status=previous,
                    to_status=target_status,
                    note=note,
                    checked_at=checked_at,
                    evidence_json=evidence,
                )
            )
            return json_data(
                {
                    "order_id": order_id,
                    "device_id": order.device_id,
                    "reason_code": order.reason_code,
                    "status": order.status,
                    "version": order.version,
                    "closed_at": order.closed_at,
                    "alarm_id": order.alarm_id,
                }
            )

        async with self.db.sessions() as session:
            return await execute_operation(
                session,
                request_id=request_id,
                route=f"/work-orders/{order_id}/transitions",
                action="transition",
                parameters={
                    "expected_version": expected_version,
                    "target_status": target_status,
                    "note": note,
                },
                now=self.clock.now(),
                perform=apply,
            )
