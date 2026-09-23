"""User-confirmed device commands; publish after commit, verify independently of ACK."""

import asyncio
import logging
import time
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.charging.contracts import ControlAck, ControlCommand
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import ChargingSession, Device, DeviceCommand, PowerPlan, StationState
from backend.app.mqtt.client import MQTTConnection
from backend.app.operations import execute_operation
from backend.app.telemetry.queries import device_status

logger = logging.getLogger(__name__)


class ChargingControl:
    def __init__(self, db: Database, settings: Settings, clock: DataClock, mqtt: MQTTConnection):
        self.db, self.settings, self.clock, self.mqtt = db, settings, clock, mqtt
        self.tasks: dict[str, asyncio.Task] = {}
        self.deadlines: dict[str, float] = {}
        self.verification_deadlines: dict[str, float] = {}

    async def create(self, device_id: str, request_id: str, action: str, args: dict) -> dict:
        command: ControlCommand | None = None

        async def reserve(session: AsyncSession) -> dict:
            nonlocal command
            device = await session.get(Device, device_id)
            if device is None:
                raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
            busy = await session.scalar(
                select(DeviceCommand.command_id)
                .where(
                    DeviceCommand.device_id == device_id,
                    or_(
                        DeviceCommand.status == "pending",
                        and_(
                            DeviceCommand.status == "applied",
                            DeviceCommand.verification_status == "pending",
                        ),
                    ),
                )
                .limit(1)
            )
            if busy:
                raise DomainError("CONTROL_BUSY", "设备已有未确认控制", 409)
            if not self.mqtt.connected:
                raise DomainError("MQTT_UNAVAILABLE", "MQTT 连接不可用", 503)
            active = await session.scalar(
                select(ChargingSession).where(
                    ChargingSession.device_id == device_id, ChargingSession.status == "ACTIVE"
                )
            )
            station = await session.get(StationState, 1)
            command_args = dict(args)
            if action == "start_session":
                status = await device_status(session, device_id, self.clock.now(), self.settings)
                if station.executing_plan_id:
                    raise DomainError("CONTROL_BUSY", "功率计划执行中", 409)
                if active:
                    raise DomainError("SESSION_CONFLICT", "已有活动会话", 409)
                if (
                    not status["data_fresh"]
                    or status["connection_state"] != "online"
                    or status["schema_version"] != 2
                    or status["session_state"] != "IDLE"
                ):
                    raise DomainError("DEVICE_NOT_READY", "开始充电需要新鲜的 v2 空闲快照", 409)
                command_args["session_id"] = str(uuid4())
                session.add(
                    ChargingSession(
                        session_id=command_args["session_id"],
                        device_id=device_id,
                        status="ACTIVE",
                        requested_power_w=args["requested_power_w"],
                    )
                )
            elif action == "stop_session":
                if active is None or active.session_id != args["session_id"]:
                    raise DomainError("SESSION_CONFLICT", "设备没有匹配的活动会话", 409)
                if station.executing_plan_id:
                    plan = await session.get(PowerPlan, station.executing_plan_id)
                    plan.status = "PARTIAL"
                    station.executing_plan_id = None
            else:
                raise DomainError("INVALID_ARGUMENTS", "页面不能直接下发功率限制")
            device.command_generation += 1
            now = self.clock.now()
            command = ControlCommand(
                command_id=uuid4(),
                device_id=device_id,
                generation=device.command_generation,
                action=action,
                args=command_args,
                issued_at=now,
                expires_at=now + timedelta(seconds=self.settings.control_ack_timeout_seconds),
            )
            session.add(
                DeviceCommand(
                    command_id=str(command.command_id),
                    device_id=device_id,
                    generation=command.generation,
                    action=action,
                    args_json=command.args,
                    status="pending",
                    issued_at=now,
                    expires_at=command.expires_at,
                    verification_status="pending",
                )
            )
            return {"command_id": str(command.command_id), "session_id": command_args["session_id"]}

        async with self.db.sessions() as session:
            result = await execute_operation(
                session,
                request_id=request_id,
                route=f"/devices/{device_id}/charging/{action}",
                action=action,
                parameters=args,
                now=self.clock.now(),
                perform=reserve,
            )
        if command is not None:
            await self.publish_committed(command)
        return result

    async def publish_committed(self, command: ControlCommand) -> None:
        """Called only by user-operation services after the command transaction commits."""
        command_id = str(command.command_id)
        self.deadlines[command_id] = time.monotonic() + self.settings.control_ack_timeout_seconds
        if not self.mqtt.publish(
            f"{self.settings.mqtt_topic_prefix}/devices/{command.device_id}/control/set",
            command.model_dump_json(),
        ):
            await self._finish(command_id, "interrupted", "MQTT_PUBLISH_FAILED")
            self.deadlines.pop(command_id, None)
            raise DomainError("MQTT_UNAVAILABLE", "发布失败，原请求可查询；不自动重发", 503)
        task = asyncio.create_task(self._monitor(command_id), name="charging-" + command_id)
        self.tasks[command_id] = task
        task.add_done_callback(lambda completed: self._task_done(command_id, completed))

    def _task_done(self, command_id: str, task: asyncio.Task) -> None:
        self.tasks.pop(command_id, None)
        self.deadlines.pop(command_id, None)
        self.verification_deadlines.pop(command_id, None)
        if not task.cancelled() and task.exception():
            logger.error(
                "CONTROL_TASK_FAILED command_id=%s error_type=%s",
                command_id,
                type(task.exception()).__name__,
            )

    async def _finish(self, command_id: str, status: str, error: str | None) -> None:
        async with self.db.sessions.begin() as session:
            row = await session.get(DeviceCommand, command_id)
            if row is None:
                return
            if row.status == "pending":
                row.status, row.error_code = status, error
            if row.verification_status == "pending":
                row.verification_status = "unconfirmed"

    async def ack(self, ack: ControlAck, topic: str) -> None:
        if topic != f"{self.settings.mqtt_topic_prefix}/devices/{ack.device_id}/control/ack":
            return
        command_id = str(ack.command_id)
        async with self.db.sessions.begin() as session:
            row = await session.get(DeviceCommand, command_id)
            if row is None or (
                row.device_id,
                row.generation,
                row.action,
                row.args_json,
                row.issued_at,
                row.expires_at,
            ) != (
                ack.device_id,
                ack.generation,
                ack.action,
                ack.args,
                ack.issued_at,
                ack.expires_at,
            ):
                return
            if row.status != "pending" or time.monotonic() > self.deadlines.get(command_id, 0):
                row.late_ack_json = ack.model_dump(mode="json")
                return
            row.status, row.ack_at, row.ack_json = (
                ack.status,
                self.clock.now(),
                ack.model_dump(mode="json"),
            )
            row.error_code = ack.error_code
            if ack.status == "applied":
                self.verification_deadlines[command_id] = (
                    time.monotonic() + self.settings.control_verification_timeout_seconds
                )
            if ack.status == "rejected":
                row.verification_status = "unconfirmed"
                if row.action == "start_session":
                    charging = await session.get(ChargingSession, row.args_json["session_id"])
                    if charging.report_seq == 0:
                        charging.status = "INTERRUPTED"
                        charging.end_reason = "CONTROL_REJECTED"

    async def _monitor(self, command_id: str) -> None:
        try:
            while True:
                async with self.db.sessions() as session:
                    row = await session.get(DeviceCommand, command_id)
                    status, action, args, generation = (
                        row.status,
                        row.action,
                        row.args_json,
                        row.generation,
                    )
                    device_id = row.device_id
                now = time.monotonic()
                if status == "pending":
                    if now >= self.deadlines[command_id]:
                        await self._finish(command_id, "timed_out", "CONTROL_TIMEOUT")
                        return
                elif status == "applied":
                    verification_deadline = self.verification_deadlines[command_id]
                    async with asyncio.timeout(max(0, verification_deadline - time.monotonic())):
                        async with self.db.sessions.begin() as session:
                            state = await device_status(
                                session, device_id, self.clock.now(), self.settings
                            )
                            matches = (
                                state["data_fresh"]
                                and state["applied_control_generation"] == generation
                            )
                            if action == "start_session":
                                matches = (
                                    matches
                                    and state["session_id"] == args["session_id"]
                                    and state["session_state"] == "ACTIVE"
                                    and state["power_limit_w"] == 0
                                    and state["requested_power_w"] == args["requested_power_w"]
                                )
                            elif action == "stop_session":
                                charging = await session.get(ChargingSession, args["session_id"])
                                matches = (
                                    matches
                                    and state["power_limit_w"] == 0
                                    and state["session_state"]
                                    in {"IDLE", "COMPLETED", "INTERRUPTED"}
                                    and charging.status in {"COMPLETED", "INTERRUPTED"}
                                )
                            else:
                                matches = (
                                    matches and state["power_limit_w"] == args["power_limit_w"]
                                )
                            matches = matches and time.monotonic() < verification_deadline
                            if matches or time.monotonic() >= verification_deadline:
                                current = await session.get(DeviceCommand, command_id)
                                current.verification_status = (
                                    "verified" if matches else "unconfirmed"
                                )
                                current.verification_json = (
                                    {
                                        "message_id": state["message_id"],
                                        "sample_ts": state["sample_ts"].isoformat()
                                        if state["sample_ts"]
                                        else None,
                                        "checked_at": self.clock.now().isoformat(),
                                    }
                                    if matches
                                    else None
                                )
                                return
                else:
                    return
                await asyncio.sleep(0.05)
        except TimeoutError:
            await self._finish(command_id, "applied", "EFFECT_UNCONFIRMED")
        except asyncio.CancelledError:
            await self._finish(command_id, "interrupted", "PROCESS_STOPPED")
            raise

    async def get(self, command_id: str) -> dict:
        async with self.db.sessions() as session:
            row = await session.get(DeviceCommand, command_id)
            if row is None:
                raise DomainError("COMMAND_NOT_FOUND", "命令不存在", 404)
            return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
