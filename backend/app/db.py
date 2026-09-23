from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import event, text, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS
from backend.app.migrations import migrate
from backend.app.models import (
    AgentRun,
    Device,
    DeviceCommand,
    PowerPlan,
    ScenarioCommandRow,
    StationState,
    ToolCall,
)


class Database:
    def __init__(self, settings: Settings):
        url = make_url(settings.database_url)
        if url.drivername != "sqlite+aiosqlite" or not url.database or url.database == ":memory:":
            raise ValueError("A local SQLite file is required (WAL)")
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        @event.listens_for(self.engine.sync_engine, "connect")
        def configure_connection(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={settings.db_busy_timeout_ms}")
            cursor.close()

    async def initialize(self, clock: DataClock | None = None) -> None:
        async with self.engine.connect() as connection:
            mode = (await connection.execute(text("PRAGMA journal_mode=WAL"))).scalar()
            if mode != "wal":
                raise RuntimeError("SQLite WAL could not be enabled")
            await connection.commit()
            await migrate(connection)
        async with self.sessions.begin() as session:
            for device_id in DEVICE_IDS:
                await session.execute(
                    insert(Device)
                    .values(device_id=device_id, name=f"充电桩 {device_id}")
                    .on_conflict_do_nothing(index_elements=["device_id"])
                )
            await session.execute(update(Device).values(last_live_received_at=None))
            await session.execute(
                update(PowerPlan)
                .where(PowerPlan.status == "EXECUTING")
                .values(status="INTERRUPTED", finished_at=(clock or DataClock()).now())
            )
            await session.execute(update(StationState).values(executing_plan_id=None))
            await session.execute(
                update(DeviceCommand)
                .where(DeviceCommand.status == "pending")
                .values(
                    status="interrupted",
                    verification_status="unconfirmed",
                    error_code="PROCESS_RESTARTED",
                )
            )
            await session.execute(
                update(DeviceCommand)
                .where(
                    DeviceCommand.status == "applied",
                    DeviceCommand.verification_status == "pending",
                )
                .values(verification_status="unconfirmed")
            )
            await session.execute(
                update(ScenarioCommandRow)
                .where(ScenarioCommandRow.status == "pending")
                .values(status="timed_out", error="PROCESS_RESTARTED_RESULT_UNCONFIRMED")
            )
            await session.execute(
                update(ToolCall)
                .where(ToolCall.status == "running")
                .values(status="failed", error_code="PROCESS_RESTARTED")
            )
            await session.execute(
                update(AgentRun)
                .where(AgentRun.status.in_(["queued", "running"]))
                .values(
                    status="interrupted",
                    error_code="PROCESS_RESTARTED",
                    finished_at=(clock or DataClock()).now(),
                )
            )

    async def close(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessions() as session:
        yield session
