"""Managed periodic submission. No queue, catch-up, model retries or independent run slot."""

import asyncio
import logging
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.scheduler import RunScheduler
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import PatrolSchedule
from backend.app.operations import execute_operation


class PatrolService:
    def __init__(self, db: Database, settings: Settings, clock: DataClock, scheduler: RunScheduler):
        self.db, self.settings, self.clock, self.scheduler = db, settings, clock, scheduler

    @staticmethod
    def data(row: PatrolSchedule) -> dict:
        return {column.name: getattr(row, column.name) for column in row.__table__.columns}

    async def initialize(self) -> None:
        async with self.db.sessions.begin() as session:
            row = await session.get(PatrolSchedule, 1)
            row.interval_seconds = self.settings.patrol_interval_seconds
            row.window_minutes = self.settings.patrol_window_minutes
            row.next_due_at = (
                self.clock.now() + timedelta(seconds=row.interval_seconds) if row.enabled else None
            )

    async def get(self) -> dict:
        async with self.db.sessions() as session:
            return self.data(await session.get(PatrolSchedule, 1))

    async def change(self, request_id: str, expected_version: int, enabled: bool) -> dict:
        async def perform(session: AsyncSession) -> dict:
            row = await session.get(PatrolSchedule, 1)
            if row.version != expected_version:
                raise DomainError("VERSION_CONFLICT", "巡检计划已被修改，请刷新", 409)
            row.enabled = enabled
            row.version += 1
            row.next_due_at = (
                self.clock.now() + timedelta(seconds=row.interval_seconds) if enabled else None
            )
            from backend.app.api import json_data

            return json_data(self.data(row))

        async with self.db.sessions() as session:
            return await execute_operation(
                session,
                request_id=request_id,
                route="/patrol-schedule",
                action="update",
                parameters={"expected_version": expected_version, "enabled": enabled},
                now=self.clock.now(),
                perform=perform,
            )

    async def tick(self) -> dict | None:
        schedule = await self.get()
        due = schedule["next_due_at"]
        if not schedule["enabled"] or due is None or due > self.clock.now():
            return None
        request_id = str(uuid5(NAMESPACE_URL, "charge-ops:patrol:1:" + due.isoformat()))
        try:
            return await self.scheduler.reserve_patrol(
                request_id,
                schedule["window_minutes"],
                due_at=due,
                schedule_version=schedule["version"],
            )
        except DomainError as error:
            if error.code != "STALE_SCHEDULE":
                raise
            return None

    async def run_timer(self) -> None:
        while True:
            await asyncio.sleep(1)
            try:
                await self.tick()
            except (DomainError, SQLAlchemyError) as error:
                logging.getLogger(__name__).error(
                    "PATROL_TIMER_ERROR type=%s", type(error).__name__
                )
