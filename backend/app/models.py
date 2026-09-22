from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCTime(TypeDecorator):
    """Fixed-width UTC strings preserve SQLite ordering and timezone on round-trip."""

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime is not allowed")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def process_result_value(self, value: str | None, dialect):
        return datetime.fromisoformat(value) if value else None


class Base(DeclarativeBase):
    pass


class Device(Base):
    __tablename__ = "devices"
    device_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str]
    latest_telemetry_id: Mapped[int | None] = mapped_column(ForeignKey("telemetry.id"))
    last_live_received_at: Mapped[datetime | None] = mapped_column(UTCTime)


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        UniqueConstraint("device_id", "boot_id", "seq"),
        Index("ix_telemetry_device_ts", "device_id", "ts"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String, unique=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    boot_id: Mapped[str]
    seq: Mapped[int]
    schema_version: Mapped[int] = mapped_column(default=1)
    ts: Mapped[datetime] = mapped_column(UTCTime)
    received_at: Mapped[datetime] = mapped_column(UTCTime)
    temperature_c: Mapped[float]
    voltage_v: Mapped[float]
    current_a: Mapped[float]
    power_kw: Mapped[float]
    operating_state: Mapped[str]


class ScenarioCommandRow(Base):
    __tablename__ = "scenario_commands"
    command_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    scenario: Mapped[str]
    status: Mapped[str]
    requested_at: Mapped[datetime] = mapped_column(UTCTime)
    ack_at: Mapped[datetime | None] = mapped_column(UTCTime)
    error: Mapped[str | None]
    late_ack_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    request_id: Mapped[str] = mapped_column(String, unique=True)
    request_hash: Mapped[str]
    question: Mapped[str] = mapped_column(Text)
    allow_work_order: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str]
    answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCTime)
    error_code: Mapped[str | None]
    messages_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    model_metrics_json: Mapped[list[dict]] = mapped_column(JSON, default=list)


class ToolCall(Base):
    __tablename__ = "tool_calls"
    tool_call_id: Mapped[str] = mapped_column(String, primary_key=True)
    provider_call_id: Mapped[str]
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"), index=True)
    tool_name: Mapped[str]
    args_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(UTCTime)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None]


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index(
            "uq_open_device_reason",
            "device_id",
            "reason_code",
            unique=True,
            sqlite_where=text("status = 'OPEN'"),
        ),
    )
    order_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    reason_code: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_from_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"))
    created_at: Mapped[datetime] = mapped_column(UTCTime)


class DiagnosticEvent(Base):
    __tablename__ = "diagnostic_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str]
    device_id: Mapped[str | None]
    received_at: Mapped[datetime] = mapped_column(UTCTime)
    summary: Mapped[str]
