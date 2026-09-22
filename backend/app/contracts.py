from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

DEVICE_IDS = ("CHG-001", "CHG-002", "CHG-003")
DeviceID = Literal["CHG-001", "CHG-002", "CHG-003"]
Scenario = Literal["normal", "overheat", "offline"]
ReasonCode = Literal["OVERHEAT", "OFFLINE"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TelemetryMessage(Contract):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    device_id: DeviceID
    message_id: UUID
    boot_id: UUID
    seq: Annotated[int, Field(strict=True, gt=0)]
    ts: AwareDatetime
    temperature_c: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-20, le=120)]
    voltage_v: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=1000)]
    current_a: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=300)]
    power_kw: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=300)]
    operating_state: Literal["idle", "charging", "fault"]

    @field_validator("ts", mode="before")
    @classmethod
    def timestamp_is_iso_or_datetime(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Timestamp must be a timezone-aware ISO string")
        return value

    @field_validator("ts")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


def parse_telemetry(
    payload: bytes, topic: str, now: datetime, prefix: str = "charge/v1"
) -> TelemetryMessage:
    if len(payload) > 8192:
        raise ValueError("PAYLOAD_TOO_LARGE")
    message = TelemetryMessage.model_validate_json(payload)
    if topic != f"{prefix}/devices/{message.device_id}/telemetry":
        raise ValueError("TOPIC_MISMATCH")
    age = (now - message.ts).total_seconds()
    if age < -5 or age > 86400:
        raise ValueError("TIMESTAMP_OUT_OF_RANGE")
    return message


class ToolContext(Contract):
    run_id: UUID
    tool_call_id: UUID
    allow_work_order: bool = Field(default=False, strict=True)


class ScenarioCommand(Contract):
    command_id: UUID
    device_id: DeviceID
    scenario: Scenario


class ScenarioAck(ScenarioCommand):
    applied_at: AwareDatetime
    status: Literal["applied", "rejected"]
