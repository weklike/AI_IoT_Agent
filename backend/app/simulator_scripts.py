"""Explicit, cancellable 20/20/20 second scenario sequences over the existing ACK path."""

import asyncio
import logging
import time
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clocks import DataClock
from backend.app.contracts import DEVICE_IDS, Scenario
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import ScenarioCommandRow, ScenarioScript
from backend.app.operations import execute_operation
from backend.app.simulator_control import ScenarioControl

SCRIPTS = {
    "normal_overheat_normal": ("normal", "overheat", "normal"),
    "normal_offline_normal": ("normal", "offline", "normal"),
}


class ScenarioScripts:
    def __init__(self, db: Database, clock: DataClock, control: ScenarioControl):
        self.db, self.clock, self.control = db, clock, control
        self.lock = asyncio.Lock()
        self.tasks: dict[str, asyncio.Task] = {}
        self.closing = False

    async def start(self, request_id: str, device_id: str, script_name: str) -> dict:
        created = False
        async with self.lock:

            async def perform(session: AsyncSession) -> dict:
                nonlocal created
                if device_id not in DEVICE_IDS:
                    raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
                if script_name not in SCRIPTS:
                    raise DomainError("INVALID_ARGUMENTS", "未知固定脚本", 422)
                if self.closing:
                    raise DomainError("SHUTTING_DOWN", "服务正在关闭", 503)
                existing = await session.scalar(
                    select(ScenarioScript).where(
                        ScenarioScript.device_id == device_id, ScenarioScript.status == "running"
                    )
                )
                if existing:
                    raise DomainError("SCRIPT_BUSY", "设备已有运行中的脚本", 409)
                if not self.control.publisher.connected:
                    raise DomainError("MQTT_UNAVAILABLE", "Broker未连接，未启动脚本", 503)
                identifier = str(uuid4())
                session.add(
                    ScenarioScript(
                        script_id=identifier,
                        device_id=device_id,
                        script_name=script_name,
                        status="running",
                        created_at=self.clock.now(),
                        steps_json=[],
                    )
                )
                created = True
                return {"script_id": identifier}

            async with self.db.sessions() as session:
                result = await execute_operation(
                    session,
                    request_id=request_id,
                    route="/simulator/scripts",
                    action="start",
                    parameters={"device_id": device_id, "script_name": script_name},
                    now=self.clock.now(),
                    perform=perform,
                )
            if created:
                identifier = result["script_id"]
                task = asyncio.create_task(
                    self._run(identifier, device_id, script_name), name="script-" + identifier
                )
                self.tasks[identifier] = task
                task.add_done_callback(lambda done, key=identifier: self._done(key, done))
            return result

    def _done(self, identifier: str, task: asyncio.Task) -> None:
        self.tasks.pop(identifier, None)
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).error(
                "SCRIPT_TASK_FAILED script_id=%s error_type=%s",
                identifier,
                type(task.exception()).__name__,
            )

    async def _finish(self, identifier: str, status: str, reason: str | None = None) -> None:
        async with self.db.sessions.begin() as session:
            await session.execute(
                update(ScenarioScript)
                .where(ScenarioScript.script_id == identifier, ScenarioScript.status == "running")
                .values(status=status, cancel_reason=reason)
            )

    async def _run(self, identifier: str, device_id: str, name: str) -> None:
        anchor = time.monotonic()
        try:
            for index, scenario in enumerate(SCRIPTS[name]):
                await asyncio.sleep(max(0, anchor + 20 * index - time.monotonic()))
                async with self.lock:

                    async def record(session: AsyncSession, command_id: str) -> None:
                        row = await session.get(ScenarioScript, identifier)
                        if row.status != "running":
                            raise DomainError("SCRIPT_STOPPED", "脚本已停止", 409)
                        row.steps_json = [
                            *row.steps_json,
                            {
                                "scenario": scenario,
                                "offset_seconds": 20 * index,
                                "command_id": command_id,
                                "status": "pending",
                            },
                        ]

                    command = await self.control.create(device_id, scenario, on_created=record)
                while True:
                    state = await self.control.get(command["command_id"])
                    if state["status"] != "pending":
                        break
                    await asyncio.sleep(0.05)
                async with self.db.sessions.begin() as session:
                    row = await session.get(ScenarioScript, identifier)
                    steps = [dict(step) for step in row.steps_json]
                    steps[index]["status"] = state["status"]
                    row.steps_json = steps
                if state["status"] != "applied":
                    await self._finish(
                        identifier, "failed", state["error"] or "SCENARIO_NOT_APPLIED"
                    )
                    return
            await asyncio.sleep(max(0, anchor + 60 - time.monotonic()))
            await self._finish(identifier, "completed")
        except asyncio.CancelledError:
            await self._finish(identifier, "interrupted", "PROCESS_INTERRUPTED")
            raise
        except (DomainError, SQLAlchemyError) as error:
            await self._finish(
                identifier,
                "failed",
                error.code if isinstance(error, DomainError) else "DATABASE_UNAVAILABLE",
            )

    async def _cancel_task(self, identifier: str) -> None:
        task = self.tasks.get(identifier)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def cancel(self, request_id: str, identifier: str) -> dict:
        async with self.lock:

            async def perform(session: AsyncSession) -> dict:
                row = await session.get(ScenarioScript, identifier)
                if row is None:
                    raise DomainError("SCRIPT_NOT_FOUND", "脚本不存在", 404)
                if row.status == "running":
                    row.status, row.cancel_reason = "cancelled", "USER_CANCELLED"
                return {"script_id": identifier, "status": row.status}

            async with self.db.sessions() as session:
                result = await execute_operation(
                    session,
                    request_id=request_id,
                    route=f"/simulator/scripts/{identifier}/cancel",
                    action="cancel",
                    parameters={},
                    now=self.clock.now(),
                    perform=perform,
                )
            await self._cancel_task(identifier)
            return result

    async def manual(self, device_id: str, scenario: Scenario) -> dict:
        async with self.lock:
            if self.closing:
                raise DomainError("SHUTTING_DOWN", "服务正在关闭", 503)
            async with self.db.sessions.begin() as session:
                row = await session.scalar(
                    select(ScenarioScript).where(
                        ScenarioScript.device_id == device_id, ScenarioScript.status == "running"
                    )
                )
                identifier = row.script_id if row else None
                if row:
                    row.status, row.cancel_reason = "cancelled", "MANUAL_SCENARIO_OVERRIDE"
            if identifier:
                await self._cancel_task(identifier)
            return await self.control.create(device_id, scenario)

    async def get(self, identifier: str) -> dict:
        async with self.db.sessions() as session:
            row = await session.get(ScenarioScript, identifier)
            if row is None:
                raise DomainError("SCRIPT_NOT_FOUND", "脚本不存在", 404)
            result = {column.name: getattr(row, column.name) for column in row.__table__.columns}
            commands = []
            for step in row.steps_json:
                command = await session.get(ScenarioCommandRow, step["command_id"])
                commands.append(
                    {
                        key: getattr(command, key)
                        for key in (
                            "command_id",
                            "scenario",
                            "status",
                            "requested_at",
                            "ack_at",
                            "ack_received_at",
                            "error",
                        )
                    }
                )
            result["commands"] = commands
            return result

    async def close(self) -> None:
        self.closing = True
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
