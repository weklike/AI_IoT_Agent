"""Deterministic alarms updated in the telemetry transaction, never by a model."""

import asyncio
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.alarms.rules import observe_duration
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import DEVICE_IDS
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import Alarm, AlarmEvent, AlarmRule, Telemetry
from backend.app.operations import execute_operation
from backend.app.telemetry.queries import device_status


def rule_data(rule: AlarmRule) -> dict:
    return {
        name: getattr(rule, name)
        for name in (
            "device_id",
            "reason_code",
            "enabled",
            "version",
            "trigger_duration_seconds",
            "clear_below_c",
            "clear_duration_seconds",
        )
    }


def alarm_data(alarm: Alarm) -> dict:
    return {
        column.name: getattr(alarm, column.name)
        for column in alarm.__table__.columns
        if column.name != "observation_json"
    }


def event(
    session: AsyncSession,
    alarm: Alarm,
    kind: str,
    observed_at: datetime,
    received_at: datetime,
    evidence: dict,
) -> None:
    session.add(
        AlarmEvent(
            event_id=str(uuid4()),
            alarm_id=alarm.alarm_id,
            device_id=alarm.device_id,
            event_type=kind,
            observed_at=observed_at,
            received_at=received_at,
            evidence_json=evidence,
        )
    )


class AlarmService:
    def __init__(self, db: Database, settings: Settings, clock: DataClock):
        self.db, self.settings, self.clock = db, settings, clock

    async def _active(self, session: AsyncSession, device_id: str, reason: str) -> Alarm | None:
        return await session.scalar(
            select(Alarm).where(
                Alarm.device_id == device_id,
                Alarm.reason_code == reason,
                Alarm.condition == "ACTIVE",
            )
        )

    async def interrupt(self, session: AsyncSession, device_id: str) -> None:
        rule = await session.get(AlarmRule, (device_id, "OVERHEAT"))
        rule.observation_json = None
        alarm = await self._active(session, device_id, "OVERHEAT")
        if alarm:
            alarm.observation_json = None

    async def observe(
        self, session: AsyncSession, sample: Telemetry, received_at: datetime
    ) -> None:
        evidence = {
            "message_id": sample.message_id,
            "sample_ts": sample.ts.isoformat(),
            "temperature_c": sample.temperature_c,
        }
        offline = await self._active(session, sample.device_id, "OFFLINE")
        if offline:
            self._clear(session, offline, sample.ts, received_at, evidence)
        rule = await session.get(AlarmRule, (sample.device_id, "OVERHEAT"))
        active = await self._active(session, sample.device_id, "OVERHEAT")
        if active:
            rule.observation_json = None
            active.evaluation_state = "known"
            active.observed_at = sample.ts
            active.peak_temperature_c = max(
                active.peak_temperature_c or sample.temperature_c, sample.temperature_c
            )
            active.evidence_json = evidence
            active.observation_json, clear = observe_duration(
                active.observation_json,
                sample.ts,
                sample.temperature_c < active.rule_json["clear_below_c"],
                active.rule_json["clear_duration_seconds"],
                self.settings.alarm_max_sample_gap_seconds,
            )
            if clear:
                self._clear(session, active, sample.ts, received_at, evidence)
        else:
            rule.observation_json, trigger = observe_duration(
                rule.observation_json,
                sample.ts,
                rule.enabled and sample.temperature_c >= self.settings.overheat_threshold_c,
                rule.trigger_duration_seconds,
                self.settings.alarm_max_sample_gap_seconds,
            )
            if trigger:
                active = Alarm(
                    alarm_id=str(uuid4()),
                    device_id=sample.device_id,
                    reason_code="OVERHEAT",
                    condition="ACTIVE",
                    evaluation_state="known",
                    peak_temperature_c=sample.temperature_c,
                    started_at=sample.ts,
                    observed_at=sample.ts,
                    rule_json=rule_data(rule),
                    evidence_json=evidence,
                    version=1,
                )
                session.add(active)
                await session.flush()
                event(session, active, "CREATED", sample.ts, received_at, evidence)

    @staticmethod
    def _clear(
        session: AsyncSession,
        alarm: Alarm,
        observed_at: datetime,
        received_at: datetime,
        evidence: dict,
    ) -> None:
        alarm.condition = "CLEARED"
        alarm.evaluation_state = "known"
        alarm.cleared_at = observed_at
        alarm.observed_at = observed_at
        alarm.version += 1
        alarm.observation_json = None
        alarm.evidence_json = evidence
        event(session, alarm, "CLEARED", observed_at, received_at, evidence)

    async def evaluate_time(self) -> None:
        now = self.clock.now()
        async with self.db.sessions() as session:
            await session.execute(text("BEGIN IMMEDIATE"))
            for device_id in DEVICE_IDS:
                state = await device_status(session, device_id, now, self.settings)
                if not state["data_fresh"]:
                    await self.interrupt(session, device_id)
                    heat = await self._active(session, device_id, "OVERHEAT")
                    if heat:
                        heat.evaluation_state = "unknown"
                offline = await self._active(session, device_id, "OFFLINE")
                if state["connection_state"] == "unknown" and offline:
                    offline.evaluation_state = "unknown"
                rule = await session.get(AlarmRule, (device_id, "OFFLINE"))
                if state["connection_state"] == "offline" and offline is None and rule.enabled:
                    evidence = {
                        "message_id": state["message_id"],
                        "sample_ts": state["sample_ts"].isoformat() if state["sample_ts"] else None,
                        "last_live_received_at": state["last_live_received_at"].isoformat(),
                        "checked_at": now.isoformat(),
                    }
                    offline = Alarm(
                        alarm_id=str(uuid4()),
                        device_id=device_id,
                        reason_code="OFFLINE",
                        condition="ACTIVE",
                        evaluation_state="known",
                        started_at=now,
                        observed_at=now,
                        rule_json=rule_data(rule),
                        evidence_json=evidence,
                        version=1,
                    )
                    session.add(offline)
                    await session.flush()
                    event(session, offline, "CREATED", now, now, evidence)
            await session.commit()

    async def acknowledge(self, alarm_id: str, request_id: str, expected_version: int) -> dict:
        async def apply(session: AsyncSession) -> dict:
            alarm = await session.get(Alarm, alarm_id)
            if alarm is None:
                raise DomainError("ALARM_NOT_FOUND", "告警不存在", 404)
            if alarm.version != expected_version:
                raise DomainError("VERSION_CONFLICT", "告警版本已变化", 409)
            if alarm.acknowledged_at is None:
                alarm.acknowledged_at = self.clock.now()
                alarm.version += 1
                event(
                    session,
                    alarm,
                    "ACKNOWLEDGED",
                    self.clock.now(),
                    self.clock.now(),
                    {"request_id": request_id},
                )
            from pydantic_core import to_jsonable_python

            return to_jsonable_python(alarm_data(alarm))

        async with self.db.sessions() as session:
            return await execute_operation(
                session,
                request_id=request_id,
                route=f"/alarms/{alarm_id}/acknowledge",
                action="acknowledge",
                parameters={"expected_version": expected_version},
                now=self.clock.now(),
                perform=apply,
            )

    async def get_rule(self, device_id: str, reason: str) -> dict:
        async with self.db.sessions() as session:
            rule = await session.get(AlarmRule, (device_id, reason))
            if rule is None:
                raise DomainError("RULE_NOT_FOUND", "规则不存在", 404)
            return rule_data(rule)

    async def change_rule(
        self, device_id: str, reason: str, request_id: str, expected_version: int, changes: dict
    ) -> dict:
        allowed = (
            {"enabled", "trigger_duration_seconds", "clear_below_c", "clear_duration_seconds"}
            if reason == "OVERHEAT"
            else {"enabled"}
        )
        if not changes or set(changes) - allowed:
            raise DomainError("INVALID_ARGUMENTS", "规则字段不符合合同")

        async def apply(session: AsyncSession) -> dict:
            rule = await session.get(AlarmRule, (device_id, reason))
            if rule is None:
                raise DomainError("RULE_NOT_FOUND", "规则不存在", 404)
            if rule.version != expected_version:
                raise DomainError("VERSION_CONFLICT", "规则版本已变化", 409)
            before = rule_data(rule)
            for key, value in changes.items():
                setattr(rule, key, value)
            rule.version += 1
            rule.updated_at = self.clock.now()
            rule.observation_json = None
            result = rule_data(rule)
            session.add(
                AlarmEvent(
                    event_id=str(uuid4()),
                    alarm_id=None,
                    device_id=device_id,
                    event_type="RULE_CHANGED",
                    observed_at=self.clock.now(),
                    received_at=self.clock.now(),
                    evidence_json={"before": before, "after": result, "request_id": request_id},
                )
            )
            return result

        async with self.db.sessions() as session:
            return await execute_operation(
                session,
                request_id=request_id,
                route=f"/alarm-rules/{device_id}/{reason}",
                action="change_rule",
                parameters={"expected_version": expected_version, **changes},
                now=self.clock.now(),
                perform=apply,
            )

    async def run_timer(self) -> None:
        import logging

        from sqlalchemy.exc import SQLAlchemyError

        while True:
            await asyncio.sleep(1)
            try:
                await self.evaluate_time()
            except SQLAlchemyError as error:
                logging.getLogger(__name__).error(
                    "ALARM_TIMER_DATABASE_ERROR type=%s", type(error).__name__
                )
