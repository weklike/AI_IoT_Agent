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
from backend.app.models import AgentRun, Base, Device


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
        async with self.engine.begin() as connection:
            mode = (await connection.execute(text("PRAGMA journal_mode=WAL"))).scalar()
            if mode != "wal":
                raise RuntimeError("SQLite WAL could not be enabled")
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions.begin() as session:
            for device_id in DEVICE_IDS:
                await session.execute(
                    insert(Device)
                    .values(device_id=device_id, name=f"充电桩 {device_id}")
                    .on_conflict_do_nothing(index_elements=["device_id"])
                )
            await session.execute(update(Device).values(last_live_received_at=None))
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
