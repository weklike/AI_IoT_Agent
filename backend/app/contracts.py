from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

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


class TelemetryV2(TelemetryMessage):
    schema_version: Annotated[int, Field(strict=True, ge=2, le=2)]
    session_id: UUID | None
    session_state: Literal["IDLE", "ACTIVE", "COMPLETED", "INTERRUPTED"]
    requested_power_w: Annotated[int, Field(strict=True, ge=0, le=20000)]
    power_limit_w: Annotated[int, Field(strict=True, ge=0, le=20000)]
    meter_total_wh: Annotated[int, Field(strict=True, ge=0)]
    session_energy_wh: Annotated[int, Field(strict=True, ge=0)] | None
    applied_control_generation: Annotated[int, Field(strict=True, ge=0)]

    @model_validator(mode="after")
    def consistent_session(self) -> "TelemetryV2":
        if self.session_state == "IDLE":
            if (
                self.session_id is not None
                or self.session_energy_wh is not None
                or self.requested_power_w
                or self.power_limit_w
            ):
                raise ValueError("Idle telemetry cannot contain an active session or power")
        elif self.session_id is None or self.session_energy_wh is None:
            raise ValueError("Session identity and energy are required")
        actual_w = (
            min(self.requested_power_w, self.power_limit_w) if self.session_state == "ACTIVE" else 0
        )
        if (
            self.voltage_v != 400
            or abs(self.power_kw * 1000 - actual_w) > 1e-6
            or abs(self.current_a * 400 - actual_w) > 1e-6
        ):
            raise ValueError("Inconsistent simulated power, voltage or current")
        if self.session_energy_wh is not None and self.session_energy_wh > self.meter_total_wh:
            raise ValueError("Session energy exceeds lifetime meter")
        return self


TELEMETRY_ADAPTER = TypeAdapter(TelemetryMessage | TelemetryV2)


def parse_telemetry(
    payload: bytes, topic: str, now: datetime, prefix: str = "charge/v1"
) -> TelemetryMessage | TelemetryV2:
    if len(payload) > 8192:
        raise ValueError("PAYLOAD_TOO_LARGE")
    message = TELEMETRY_ADAPTER.validate_json(payload)
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


class RunRequest(Contract):
    request_id: UUID
    question: Annotated[str, Field(min_length=1, max_length=2000, strict=True)]
    allow_work_order: Annotated[bool, Field(strict=True)] = False

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question must not be blank")
        return value
