from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from backend.app.contracts import Contract, DeviceID

Nonnegative = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, gt=0)]
Power = Annotated[int, Field(strict=True, ge=0, le=20000)]


class SessionReportMessage(Contract):
    report_id: UUID
    device_id: DeviceID
    session_id: UUID
    report_seq: Positive
    started_at: AwareDatetime
    observed_at: AwareDatetime
    ended_at: AwareDatetime | None
    status: Literal["ACTIVE", "COMPLETED", "INTERRUPTED"]
    start_meter_wh: Nonnegative
    end_meter_wh: Nonnegative
    energy_wh: Nonnegative
    end_reason: Literal["USER_STOP", "SIMULATOR_RESTART", "SIMULATOR_SHUTDOWN"] | None
    meter_quality: Literal["exact", "checkpoint"]

    @field_validator("started_at", "observed_at", "ended_at", mode="before")
    @classmethod
    def iso_time(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("Timestamp must be ISO datetime")
        return value

    @field_validator("started_at", "observed_at", "ended_at")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC) if value else None

    @model_validator(mode="after")
    def consistent(self) -> "SessionReportMessage":
        if self.started_at > self.observed_at:
            raise ValueError("Invalid observation ordering")
        if self.status == "ACTIVE":
            if self.ended_at is not None or self.end_reason is not None:
                raise ValueError("Active report cannot have an end")
        elif (
            self.ended_at is None
            or self.end_reason is None
            or not self.started_at <= self.ended_at <= self.observed_at
        ):
            raise ValueError("Terminal report requires valid end")
        if (
            self.end_meter_wh < self.start_meter_wh
            or self.energy_wh != self.end_meter_wh - self.start_meter_wh
        ):
            raise ValueError("Energy must equal the meter difference")
        return self


class SessionAck(Contract):
    report_id: UUID
    session_id: UUID
    report_seq: Positive
    status: Literal["stored", "conflict", "rejected"]


class StartArgs(Contract):
    session_id: UUID
    requested_power_w: Annotated[int, Field(strict=True, ge=100, le=20000, multiple_of=100)]


class StopArgs(Contract):
    session_id: UUID


class LimitArgs(Contract):
    power_limit_w: Annotated[int, Field(strict=True, ge=0, le=20000, multiple_of=100)]


class ControlCommand(Contract):
    command_id: UUID
    device_id: DeviceID
    generation: Positive
    action: Literal["start_session", "stop_session", "set_power_limit"]
    args: dict
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @field_validator("issued_at", "expires_at", mode="before")
    @classmethod
    def iso_control_time(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Control timestamp must be ISO datetime")
        return value

    @field_validator("issued_at", "expires_at")
    @classmethod
    def control_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def valid_action(self) -> "ControlCommand":
        schema = {
            "start_session": StartArgs,
            "stop_session": StopArgs,
            "set_power_limit": LimitArgs,
        }[self.action]
        self.args = schema.model_validate(self.args).model_dump(mode="json")
        if (self.expires_at - self.issued_at).total_seconds() != 5:
            raise ValueError("Control validity must be five seconds")
        return self


class ControlAck(ControlCommand):
    applied_at: AwareDatetime
    status: Literal["applied", "rejected"]
    error_code: str | None
    actual_state: dict
