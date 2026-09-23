import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS, Scenario, ScenarioAck, ScenarioCommand
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import ScenarioCommandRow


class Publisher(Protocol):
    connected: bool

    def publish(self, topic: str, payload: str) -> bool: ...


class ScenarioControl:
    def __init__(self, db: Database, settings: Settings, clock: DataClock, publisher: Publisher):
        self.db, self.settings, self.clock, self.publisher = db, settings, clock, publisher
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        self.deadlines: dict[str, float] = {}

    async def create(
        self,
        device_id: str,
        scenario: Scenario,
        *,
        on_created: Callable[[AsyncSession, str], Awaitable[None]] | None = None,
    ) -> dict:
        if device_id not in DEVICE_IDS:
            raise DomainError("DEVICE_NOT_FOUND", "设备不存在", 404)
        if not self.publisher.connected:
            raise DomainError("MQTT_UNAVAILABLE", "Broker 未连接，未发送命令", 503)
        command = ScenarioCommand(command_id=uuid4(), device_id=device_id, scenario=scenario)
        key = str(command.command_id)
        async with self.lock:
            async with self.db.sessions.begin() as session:
                session.add(
                    ScenarioCommandRow(
                        command_id=key,
                        device_id=device_id,
                        scenario=scenario,
                        status="pending",
                        requested_at=self.clock.now(),
                    )
                )
                if on_created is not None:
                    await on_created(session, key)
            self.deadlines[key] = time.monotonic() + self.settings.scenario_ack_timeout_seconds
            sent = self.publisher.publish(
                f"{self.settings.mqtt_topic_prefix}/devices/{device_id}/scenario/set",
                command.model_dump_json(),
            )
            if not sent:
                async with self.db.sessions.begin() as session:
                    await session.execute(
                        update(ScenarioCommandRow)
                        .where(ScenarioCommandRow.command_id == key)
                        .values(status="rejected", error="MQTT_PUBLISH_FAILED")
                    )
                self.deadlines.pop(key, None)
                raise DomainError("MQTT_UNAVAILABLE", "命令发布未获确认", 503)
            task = asyncio.create_task(self._expire(key), name=f"scenario-{key}")
            self.tasks.add(task)
            task.add_done_callback(self._task_done)
        return {"command_id": key, "status": "pending"}

    def _task_done(self, task: asyncio.Task):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger(__name__).error(
                "SCENARIO_TIMER_FAILED task=%s error_type=%s",
                task.get_name(),
                type(task.exception()).__name__,
            )

    async def _expire(self, key: str):
        try:
            await asyncio.sleep(max(0, self.deadlines[key] - time.monotonic()))
            async with self.lock:
                async with self.db.sessions.begin() as session:
                    await session.execute(
                        update(ScenarioCommandRow)
                        .where(
                            ScenarioCommandRow.command_id == key,
                            ScenarioCommandRow.status == "pending",
                        )
                        .values(status="timed_out", error="SCENARIO_ACK_TIMEOUT")
                    )
                self.deadlines.pop(key, None)
        except asyncio.CancelledError:
            raise

    async def ack(self, ack: ScenarioAck, topic: str):
        if topic != f"{self.settings.mqtt_topic_prefix}/devices/{ack.device_id}/scenario/ack":
            return
        key = str(ack.command_id)
        async with self.lock:
            async with self.db.sessions.begin() as session:
                row = await session.get(ScenarioCommandRow, key)
                if row is None or row.device_id != ack.device_id or row.scenario != ack.scenario:
                    return
                expired = key in self.deadlines and time.monotonic() > self.deadlines[key]
                if row.status == "timed_out" or (row.status == "pending" and expired):
                    row.status = "timed_out"
                    row.error = "SCENARIO_ACK_TIMEOUT"
                    row.late_ack_json = ack.model_dump(mode="json")
                    row.late_ack_observed_at = ack.applied_at
                    row.late_ack_received_at = self.clock.now()
                elif row.status == "pending":
                    row.status = ack.status
                    row.ack_at = ack.applied_at
                    row.ack_received_at = self.clock.now()

    async def get(self, command_id: str | UUID) -> dict:
        async with self.lock, self.db.sessions.begin() as session:
            row = await session.get(ScenarioCommandRow, str(command_id))
            if row is None:
                raise DomainError("COMMAND_NOT_FOUND", "场景命令不存在", 404)
            deadline = self.deadlines.get(str(command_id))
            if row.status == "pending" and deadline is not None and time.monotonic() >= deadline:
                # A timer may have hit the bounded SQLite busy timeout. A later explicit read
                # can persist the overdue terminal state; there is no hidden retry loop.
                row.status = "timed_out"
                row.error = "SCENARIO_ACK_TIMEOUT"
            return {
                field: getattr(row, field)
                for field in (
                    "command_id",
                    "device_id",
                    "scenario",
                    "status",
                    "requested_at",
                    "ack_at",
                    "error",
                    "late_ack_json",
                )
            }

    async def close(self):
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
