"""Saved power previews and bounded, parallel-per-stage decrease-before-increase plans."""

import asyncio
import logging
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.charging.contracts import ControlCommand
from backend.app.charging.control import ChargingControl
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import ChargingSession, Device, DeviceCommand, PowerPlan, StationState
from backend.app.operations import execute_operation
from backend.app.power.allocation import allocate_power
from backend.app.telemetry.queries import device_status

logger = logging.getLogger(__name__)
CONTROL_FIELDS = (
    "session_id",
    "session_state",
    "requested_power_w",
    "power_limit_w",
    "applied_control_generation",
)


class PowerService:
    def __init__(
        self, db: Database, settings: Settings, clock: DataClock, control: ChargingControl
    ):
        self.db, self.settings, self.clock, self.control = db, settings, clock, control
        self.tasks: dict[str, asyncio.Task] = {}
        self.owned: dict[str, set[str]] = {}

    async def _snapshot(self, session: AsyncSession, *, allow_pending: bool = False) -> dict:
        anchor = self.clock.now()
        states = {
            device: await device_status(session, device, anchor, self.settings)
            for device in DEVICE_IDS
        }
        for device, state in states.items():
            if (
                not state["data_fresh"]
                or state["connection_state"] != "online"
                or state["schema_version"] != 2
            ):
                raise DomainError("DEVICE_NOT_READY", f"{device} 没有可确认的新鲜功率限制", 409)
            active = await session.scalar(
                select(ChargingSession).where(
                    ChargingSession.device_id == device, ChargingSession.status == "ACTIVE"
                )
            )
            if state["session_state"] == "ACTIVE" and (
                active is None or active.session_id != state["session_id"]
            ):
                raise DomainError("SESSION_CONFLICT", f"{device} 会话尚未确认", 409)
            unresolved = (
                await session.scalars(
                    select(DeviceCommand).where(
                        DeviceCommand.device_id == device,
                        DeviceCommand.verification_status != "verified",
                    )
                )
            ).all()
            for command in unresolved:
                pending = command.status == "pending" or (
                    command.status == "applied" and command.verification_status == "pending"
                )
                if pending and not allow_pending:
                    raise DomainError("CONTROL_BUSY", f"{device} 存在未确认命令", 409)
                if (
                    command.status != "rejected"
                    and command.generation > state["applied_control_generation"]
                    and not pending
                ):
                    raise DomainError(
                        "DEVICE_NOT_READY", f"{device} 的命令结果与当前限制尚不能确认", 409
                    )
        return states

    @staticmethod
    def _fingerprint(states: dict) -> dict:
        return {
            device: {field: state[field] for field in CONTROL_FIELDS}
            for device, state in states.items()
        }

    async def preview(
        self, request_id: str, budget_w: int, strategy: str, priority: list[str] | None
    ) -> dict:
        async def create(session: AsyncSession) -> dict:
            station = await session.get(StationState, 1)
            if station.executing_plan_id:
                raise DomainError("CONTROL_BUSY", "已有执行中的功率计划", 409)
            states = await self._snapshot(session)
            demands = {
                device: state["requested_power_w"] if state["session_state"] == "ACTIVE" else 0
                for device, state in states.items()
            }
            try:
                allocation = allocate_power(budget_w, demands, strategy, priority)
            except ValueError as error:
                raise DomainError("INVALID_ARGUMENTS", str(error)) from error
            plan_id = str(uuid4())
            snapshot = {
                "fingerprint": self._fingerprint(states),
                "message_ids": {device: state["message_id"] for device, state in states.items()},
                "confirmed_budget_w": station.budget_w,
            }
            session.add(
                PowerPlan(
                    plan_id=plan_id,
                    strategy=strategy,
                    budget_w=budget_w,
                    station_revision=station.revision,
                    snapshot_json=snapshot,
                    allocation_json=allocation,
                    results_json={},
                    status="PREVIEW",
                    created_at=self.clock.now(),
                )
            )
            return {
                "plan_id": plan_id,
                "allocation_w": allocation,
                "budget_w": budget_w,
                "status": "PREVIEW",
            }

        async with self.db.sessions() as session:
            return await execute_operation(
                session,
                request_id=request_id,
                route="/power-plans",
                action="preview",
                parameters={
                    "budget_w": budget_w,
                    "strategy": strategy,
                    "device_priority": priority,
                },
                now=self.clock.now(),
                perform=create,
            )

    async def execute(self, request_id: str, plan_id: str) -> dict:
        accepted = False

        async def reserve(session: AsyncSession) -> dict:
            nonlocal accepted
            plan = await session.get(PowerPlan, plan_id)
            if plan is None:
                raise DomainError("PLAN_NOT_FOUND", "计划不存在", 404)
            station = await session.get(StationState, 1)
            if station.executing_plan_id:
                raise DomainError("CONTROL_BUSY", "已有执行中的功率计划", 409)
            if plan.status != "PREVIEW":
                raise DomainError("INVALID_TRANSITION", "计划不能再次执行", 409)
            if (
                (self.clock.now() - plan.created_at).total_seconds()
                > self.settings.power_preview_ttl_seconds
                or station.revision != plan.station_revision
            ):
                raise DomainError("PLAN_STALE", "预览已过期或站点版本发生变化", 409)
            states = await self._snapshot(session)
            if self._fingerprint(states) != plan.snapshot_json["fingerprint"]:
                raise DomainError("PLAN_STALE", "会话或控制限制发生变化，请重新预览", 409)
            plan.status = "EXECUTING"
            station.executing_plan_id = plan_id
            accepted = True
            return {"plan_id": plan_id}

        async with self.db.sessions() as session:
            result = await execute_operation(
                session,
                request_id=request_id,
                route=f"/power-plans/{plan_id}/execute",
                action="execute",
                parameters={},
                now=self.clock.now(),
                perform=reserve,
            )
        if accepted:
            self.owned[plan_id] = set()
            task = asyncio.create_task(self._run(plan_id), name="power-" + plan_id)
            self.tasks[plan_id] = task
            task.add_done_callback(lambda done: self._done(plan_id, done))
        return result

    def _done(self, plan_id: str, task: asyncio.Task) -> None:
        self.tasks.pop(plan_id, None)
        self.owned.pop(plan_id, None)
        if not task.cancelled() and task.exception():
            logger.error(
                "POWER_TASK_FAILED plan_id=%s error_type=%s",
                plan_id,
                type(task.exception()).__name__,
            )

    async def _dispatch(self, plan_id: str, device_id: str, target: int) -> str:
        async with self.db.sessions() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            plan = await session.get(PowerPlan, plan_id)
            station = await session.get(StationState, 1)
            if plan.status != "EXECUTING" or station.executing_plan_id != plan_id:
                raise DomainError("PLAN_STALE", "计划已中止", 409)
            states = await self._snapshot(session, allow_pending=True)
            original = plan.snapshot_json["fingerprint"]
            if any(
                states[device]["session_id"] != original[device]["session_id"]
                or states[device]["requested_power_w"] != original[device]["requested_power_w"]
                for device in DEVICE_IDS
            ):
                raise DomainError("PLAN_STALE", "执行期间会话发生变化", 409)
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
                raise DomainError("CONTROL_BUSY", "设备控制忙", 409)
            bounds = {device: state["power_limit_w"] for device, state in states.items()}
            pending = (
                await session.scalars(
                    select(DeviceCommand).where(
                        DeviceCommand.status.in_(["pending", "applied"]),
                        DeviceCommand.verification_status == "pending",
                    )
                )
            ).all()
            for command in pending:
                if command.action == "set_power_limit":
                    bounds[command.device_id] = max(
                        bounds[command.device_id], command.args_json["power_limit_w"]
                    )
            bounds[device_id] = max(bounds[device_id], target)
            protection = max(plan.budget_w, plan.snapshot_json["confirmed_budget_w"])
            if target > states[device_id]["power_limit_w"] and sum(bounds.values()) > protection:
                raise DomainError("PLAN_STALE", "最坏功率上界超过过渡预算", 409)
            device = await session.get(Device, device_id)
            device.command_generation += 1
            now = self.clock.now()
            command = ControlCommand(
                command_id=uuid4(),
                device_id=device_id,
                generation=device.command_generation,
                action="set_power_limit",
                args={"power_limit_w": target},
                issued_at=now,
                expires_at=now + timedelta(seconds=self.settings.control_ack_timeout_seconds),
            )
            command_id = str(command.command_id)
            self.owned[plan_id].add(command_id)
            session.add(
                DeviceCommand(
                    command_id=command_id,
                    device_id=device_id,
                    generation=command.generation,
                    action=command.action,
                    args_json=command.args,
                    status="pending",
                    issued_at=now,
                    expires_at=command.expires_at,
                    verification_status="pending",
                )
            )
            results = dict(plan.results_json)
            results[device_id] = {
                "command_id": command_id,
                "target_w": target,
                "worst_case_w": sum(bounds.values()),
                "protection_budget_w": protection,
            }
            plan.results_json = results
            await session.commit()
        await self.control.publish_committed(command)
        return command_id

    async def _wait_verified(self, command_id: str) -> None:
        while True:
            row = await self.control.get(command_id)
            if row["verification_status"] == "verified":
                return
            if row["verification_status"] == "unconfirmed" or row["status"] not in {
                "pending",
                "applied",
            }:
                raise DomainError("PLAN_PARTIAL", "设备反馈未确认", 409)
            await asyncio.sleep(0.05)

    async def _phase(self, plan_id: str, targets: dict[str, int]) -> None:
        async def apply(device: str, target: int):
            command_id = await self._dispatch(plan_id, device, target)
            await self._wait_verified(command_id)

        jobs = [asyncio.create_task(apply(device, target)) for device, target in targets.items()]
        try:
            if jobs:
                await asyncio.gather(*jobs)
        finally:
            for job in jobs:
                if not job.done():
                    job.cancel()
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)

    async def _run(self, plan_id: str) -> None:
        final = "PARTIAL"
        error = None
        try:
            async with asyncio.timeout(self.settings.power_plan_timeout_seconds):
                async with self.db.sessions() as session:
                    plan = await session.get(PowerPlan, plan_id)
                    previous = plan.snapshot_json["fingerprint"]
                    allocation = plan.allocation_json
                lower = {
                    device: target
                    for device, target in allocation.items()
                    if target < previous[device]["power_limit_w"]
                }
                higher = {
                    device: target
                    for device, target in allocation.items()
                    if target > previous[device]["power_limit_w"]
                }
                await self._phase(plan_id, lower)
                await self._phase(plan_id, higher)
                async with self.db.sessions() as session:
                    states = await self._snapshot(session)
                    if any(
                        states[device]["power_limit_w"] != target
                        for device, target in allocation.items()
                    ):
                        raise DomainError("PLAN_PARTIAL", "最终限制尚未全部确认", 409)
                final = "VERIFIED"
        except asyncio.CancelledError:
            final, error = "INTERRUPTED", "PROCESS_STOPPED"
        except (DomainError, TimeoutError) as failure:
            error = failure.code if isinstance(failure, DomainError) else "PLAN_TIMEOUT"
        except SQLAlchemyError:
            error = "DATABASE_UNAVAILABLE"
        finally:
            await self._settle_commands(plan_id)
            async with self.db.sessions() as session:
                await session.execute(text("BEGIN IMMEDIATE"))
                owned_ids = self.owned.get(plan_id, set())
                if owned_ids:
                    await session.execute(
                        update(DeviceCommand)
                        .where(
                            DeviceCommand.command_id.in_(owned_ids),
                            DeviceCommand.status == "pending",
                        )
                        .values(
                            status="interrupted",
                            verification_status="unconfirmed",
                            error_code="PLAN_STOPPED",
                        )
                    )
                    await session.execute(
                        update(DeviceCommand)
                        .where(
                            DeviceCommand.command_id.in_(owned_ids),
                            DeviceCommand.verification_status == "pending",
                        )
                        .values(verification_status="unconfirmed")
                    )
                plan = await session.get(PowerPlan, plan_id)
                station = await session.get(StationState, 1)
                if plan.finished_at is None:
                    plan.finished_at = self.clock.now()
                if plan.status == "EXECUTING":
                    plan.status = final
                    plan.finished_at = self.clock.now()
                    if final == "VERIFIED":
                        station.budget_w = plan.budget_w
                        station.revision += 1
                    if error:
                        plan.results_json = {**plan.results_json, "error_code": error}
                if station.executing_plan_id == plan_id:
                    station.executing_plan_id = None
                await session.commit()

    async def _settle_commands(self, plan_id: str) -> None:
        tasks = [
            self.control.tasks[identity]
            for identity in self.owned.get(plan_id, set())
            if identity in self.control.tasks
        ]
        if tasks:
            _, pending = await asyncio.wait(
                tasks, timeout=max(0, self.settings.power_plan_cleanup_seconds - 2)
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        # The final short transaction settles any committed-but-unpublished command in bulk.

    async def get(self, plan_id: str) -> dict:
        async with self.db.sessions() as session:
            plan = await session.get(PowerPlan, plan_id)
            if plan is None:
                raise DomainError("PLAN_NOT_FOUND", "计划不存在", 404)
            result = {column.name: getattr(plan, column.name) for column in plan.__table__.columns}
            station = await session.get(StationState, 1)
            result["confirmed_budget_w"] = station.budget_w
            result["protection_budget_w"] = max(
                plan.budget_w, plan.snapshot_json["confirmed_budget_w"]
            )
            commands = {}
            for device, item in plan.results_json.items():
                if isinstance(item, dict) and "command_id" in item:
                    row = await session.get(DeviceCommand, item["command_id"])
                    commands[device] = {
                        "command_id": row.command_id,
                        "status": row.status,
                        "verification_status": row.verification_status,
                        "error_code": row.error_code,
                    }
            result["commands"] = commands
            return result

    async def station(self) -> dict:
        async with self.db.sessions() as session:
            station = await session.get(StationState, 1)
            latest = await session.scalar(
                select(PowerPlan)
                .order_by(PowerPlan.created_at.desc(), PowerPlan.plan_id.desc())
                .limit(1)
            )
            return {
                "budget_w": station.budget_w,
                "revision": station.revision,
                "executing_plan_id": station.executing_plan_id,
                "latest_plan": {
                    "plan_id": latest.plan_id,
                    "status": latest.status,
                    "target_budget_w": latest.budget_w,
                }
                if latest
                else None,
            }

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
