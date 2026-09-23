import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from backend.app.clocks import DataClock
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import AgentRun, PatrolReport, PatrolSchedule
from backend.app.operations import execute_operation


class RunScheduler:
    def __init__(self, db: Database, clock: DataClock, execute: Callable[[str], Awaitable[None]]):
        self.db, self.clock, self.execute = db, clock, execute
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None
        self.closing = False

    async def reserve(self, request_id: str, question: str, allow_work_order: bool) -> str:
        digest = hashlib.sha256(
            json.dumps(
                {"question": question, "allow_work_order": allow_work_order},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self.lock:
            async with self.db.sessions() as session:
                existing = await session.scalar(
                    select(AgentRun).where(AgentRun.request_id == request_id)
                )
                if existing:
                    if existing.request_hash != digest:
                        raise DomainError("REQUEST_CONFLICT", "request_id 已被用于不同请求", 409)
                    return existing.run_id
                if self.closing:
                    raise DomainError("SHUTTING_DOWN", "服务正在关闭", 503)
                if self.task and not self.task.done():
                    raise DomainError("AGENT_BUSY", "已有任务正在运行", 429)
                run_id = str(uuid4())
                session.add(
                    AgentRun(
                        run_id=run_id,
                        request_id=request_id,
                        request_hash=digest,
                        question=question,
                        allow_work_order=allow_work_order,
                        status="queued",
                        created_at=self.clock.now(),
                    )
                )
                await session.commit()
                self.task = asyncio.create_task(self.execute(run_id), name=f"agent-{run_id}")
                return run_id

    async def reserve_patrol(
        self,
        request_id: str,
        window_minutes: int,
        *,
        due_at: datetime | None = None,
        schedule_version: int | None = None,
    ) -> dict:
        if type(window_minutes) is not int or window_minutes not in (10, 30, 60):
            raise DomainError("INVALID_ARGUMENTS", "巡检窗口必须为10/30/60分钟")
        created = False
        async with self.lock:

            async def perform(session):
                nonlocal created
                existing = await session.scalar(
                    select(AgentRun).where(AgentRun.request_id == request_id)
                )
                if existing:
                    raise DomainError("REQUEST_CONFLICT", "请求ID已用于其他任务", 409)
                if self.closing:
                    raise DomainError("SHUTTING_DOWN", "服务正在关闭", 503)
                now = self.clock.now()
                if due_at is not None:
                    schedule = await session.get(PatrolSchedule, 1)
                    if (
                        not schedule.enabled
                        or schedule.version != schedule_version
                        or schedule.next_due_at != due_at
                        or due_at > now
                    ):
                        raise DomainError("STALE_SCHEDULE", "巡检周期已变更或尚未到期", 409)
                    schedule.next_due_at = now + timedelta(seconds=schedule.interval_seconds)
                if self.task and not self.task.done():
                    if due_at is None:
                        raise DomainError("AGENT_BUSY", "已有任务正在运行", 429)
                    report_id = str(uuid4())
                    session.add(
                        PatrolReport(
                            report_id=report_id,
                            request_id=request_id,
                            schedule_id=1,
                            due_at=due_at,
                            trigger="scheduled",
                            status="skipped_busy",
                            window_minutes=window_minutes,
                            created_at=now,
                        )
                    )
                    return {"run_id": None, "report_id": report_id}
                run_id, report_id = str(uuid4()), str(uuid4())
                now = self.clock.now()
                session.add(
                    AgentRun(
                        run_id=run_id,
                        request_id=request_id,
                        request_hash=f"patrol:{window_minutes}",
                        kind="patrol",
                        question=f"巡检三台设备最近{window_minutes}分钟，先调用get_fleet_overview；区分观测、可能原因和建议。",
                        allow_work_order=False,
                        status="queued",
                        created_at=now,
                    )
                )
                await session.flush()
                session.add(
                    PatrolReport(
                        report_id=report_id,
                        request_id=request_id,
                        run_id=run_id,
                        trigger="scheduled" if due_at else "manual",
                        schedule_id=1 if due_at else None,
                        due_at=due_at,
                        window_minutes=window_minutes,
                        status="queued",
                        created_at=now,
                    )
                )
                created = True
                return {"run_id": run_id, "report_id": report_id}

            async with self.db.sessions() as session:
                result = await execute_operation(
                    session,
                    request_id=request_id,
                    route="/patrols",
                    action="create",
                    parameters={
                        "window_minutes": window_minutes,
                        **(
                            {"due_at": due_at.isoformat(), "schedule_version": schedule_version}
                            if due_at
                            else {}
                        ),
                    },
                    now=self.clock.now(),
                    perform=perform,
                )
            if created:
                run_id = result["run_id"]
                self.task = asyncio.create_task(self.execute(run_id), name=f"agent-{run_id}")
            return result

    async def close(self):
        self.closing = True
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
