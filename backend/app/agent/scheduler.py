import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

from sqlalchemy import select

from backend.app.clocks import DataClock
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import AgentRun


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

    async def close(self):
        self.closing = True
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
