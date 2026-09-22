import time
from pathlib import Path
from typing import Annotated

from pydantic import Field, ValidationError

from backend.app.api import json_data
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import Contract, ReasonCode, ToolContext
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import ToolCall
from backend.app.telemetry.ingest import TelemetryStore
from backend.app.work_orders import WorkOrderService


class DeviceArgs(Contract):
    device_id: Annotated[str, Field(strict=True, min_length=1, max_length=64)]


class HistoryArgs(DeviceArgs):
    window_minutes: Annotated[int, Field(strict=True, ge=1, le=60)]


class GuideArgs(Contract):
    reason_code: ReasonCode


class OrderArgs(DeviceArgs):
    reason_code: ReasonCode


ARGUMENTS = {
    "get_device_status": DeviceArgs,
    "get_device_history": HistoryArgs,
    "get_fault_guide": GuideArgs,
    "create_work_order": OrderArgs,
}
DESCRIPTIONS = {
    "get_device_status": "查询当前连接状态、新鲜度和最后指标，必须区分过期数据。",
    "get_device_history": "查询最近1—60分钟真实样本与统计。",
    "get_fault_guide": "按故障码查询版本化排查说明。",
    "create_work_order": "仅在用户明确要求且已查询有效证据后创建/复用检修工单。",
}


def schemas(allowed: bool) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": schema.model_json_schema(),
                "strict": True,
            },
        }
        for name, schema in ARGUMENTS.items()
        if allowed or name != "create_work_order"
    ]


def validate_call(call: dict, allowed: bool) -> dict:
    name = call["function"]["name"]
    if name not in ARGUMENTS:
        raise DomainError("UNKNOWN_TOOL", "模型请求了未注册工具")
    if name == "create_work_order" and not allowed:
        raise DomainError("WRITE_NOT_ALLOWED", "本次任务未授权创建工单")
    try:
        return ARGUMENTS[name].model_validate_json(call["function"]["arguments"]).model_dump()
    except ValidationError as exc:
        raise DomainError("INVALID_ARGUMENTS", "工具参数不符合合同") from exc


class ToolExecutor:
    def __init__(self, db: Database, settings: Settings, clock: DataClock, store: TelemetryStore):
        self.db, self.settings, self.clock, self.store = db, settings, clock, store
        self.orders = WorkOrderService(db, settings, clock)
        directory = Path(__file__).resolve().parents[3] / "knowledge"
        self.guides = {
            reason: {
                "source_id": f"GUIDE-{reason}",
                "version": "1.0",
                "title": "合成过温告警排查" if reason == "OVERHEAT" else "遥测静默排查",
                "content": (directory / f"{reason.lower()}.md").read_text(),
            }
            for reason in ("OVERHEAT", "OFFLINE")
        }

    async def invoke(self, name: str, args: dict, context: ToolContext) -> dict:
        if name == "get_device_status":
            data = await self.store.device_status(**args)
            if data["message_id"] is None:
                raise DomainError("NO_DATA", "设备没有样本，当前状态未知")
            return data
        if name == "get_device_history":
            return await self.store.history(**args)
        if name == "get_fault_guide":
            return self.guides[args["reason_code"]]
        if name == "create_work_order":
            return await self.orders.create(**args, context=context)
        raise DomainError("UNKNOWN_TOOL", "工具未注册")

    async def execute(
        self, call: dict, args: dict, context: ToolContext, *, ordinal: int = 0
    ) -> dict:
        name = call["function"]["name"]
        start = time.monotonic()
        async with self.db.sessions.begin() as session:
            session.add(
                ToolCall(
                    tool_call_id=str(context.tool_call_id),
                    provider_call_id=call["id"],
                    ordinal=ordinal,
                    run_id=str(context.run_id),
                    tool_name=name,
                    args_json=args,
                    status="running",
                    started_at=self.clock.now(),
                )
            )
        try:
            value = await self.invoke(name, args, context)
            result = (
                value
                if name == "create_work_order"
                else {
                    "tool_call_id": str(context.tool_call_id),
                    "ok": True,
                    "data": json_data(value),
                    "error": None,
                }
            )
        except DomainError as exc:
            result = {
                "tool_call_id": str(context.tool_call_id),
                "ok": False,
                "data": None,
                "error": {"code": exc.code, "message": exc.message},
            }
        async with self.db.sessions.begin() as session:
            row = await session.get(ToolCall, str(context.tool_call_id))
            row.result_json = result
            row.status = "succeeded" if result["ok"] else "failed"
            row.error_code = None if result["ok"] else result["error"]["code"]
            row.duration_ms = (time.monotonic() - start) * 1000
        return result
