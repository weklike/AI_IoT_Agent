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
    rated_power_w: Mapped[int] = mapped_column(default=20000, server_default="20000")
    command_generation: Mapped[int] = mapped_column(default=0, server_default="0")
    model: Mapped[str] = mapped_column(default="SIM-CHG-V2", server_default="SIM-CHG-V2")
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
    session_id: Mapped[str | None]
    session_state: Mapped[str | None]
    requested_power_w: Mapped[int | None]
    power_limit_w: Mapped[int | None]
    meter_total_wh: Mapped[int | None]
    session_energy_wh: Mapped[int | None]
    applied_control_generation: Mapped[int | None]


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
    kind: Mapped[str] = mapped_column(default="chat", server_default="chat")
    answer_refs: Mapped[list | None] = mapped_column(JSON)
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
    ordinal: Mapped[int] = mapped_column(default=0)
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
            sqlite_where=text("status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')"),
        ),
    )
    order_id: Mapped[str] = mapped_column(String, primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    reason_code: Mapped[str]
    status: Mapped[str] = mapped_column(default="OPEN")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    closed_at: Mapped[datetime | None] = mapped_column(UTCTime)
    alarm_id: Mapped[str | None] = mapped_column(ForeignKey("alarms.alarm_id"))
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


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[int] = mapped_column(primary_key=True)
    checksum: Mapped[str]
    applied_at: Mapped[datetime] = mapped_column(UTCTime)


class OperationRequest(Base):
    __tablename__ = "operation_requests"
    request_id: Mapped[str] = mapped_column(primary_key=True)
    request_hash: Mapped[str]
    route: Mapped[str]
    action: Mapped[str]
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCTime)


class DeviceCommand(Base):
    __tablename__ = "device_commands"
    __table_args__ = (UniqueConstraint("device_id", "generation"),)
    command_id: Mapped[str] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    generation: Mapped[int]
    action: Mapped[str]
    args_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str]
    issued_at: Mapped[datetime] = mapped_column(UTCTime)
    expires_at: Mapped[datetime] = mapped_column(UTCTime)
    ack_at: Mapped[datetime | None] = mapped_column(UTCTime)
    ack_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    late_ack_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    verification_status: Mapped[str] = mapped_column(default="pending")
    verification_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None]


class ChargingSession(Base):
    __tablename__ = "charging_sessions"
    __table_args__ = (
        Index(
            "uq_active_device_session",
            "device_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )
    session_id: Mapped[str] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    status: Mapped[str]
    requested_power_w: Mapped[int]
    started_at: Mapped[datetime | None] = mapped_column(UTCTime)
    observed_at: Mapped[datetime | None] = mapped_column(UTCTime)
    ended_at: Mapped[datetime | None] = mapped_column(UTCTime)
    start_meter_wh: Mapped[int | None]
    end_meter_wh: Mapped[int | None]
    energy_wh: Mapped[int | None]
    meter_quality: Mapped[str | None]
    end_reason: Mapped[str | None]
    report_seq: Mapped[int] = mapped_column(default=0)


class SessionReport(Base):
    __tablename__ = "session_reports"
    __table_args__ = (UniqueConstraint("session_id", "report_seq"),)
    report_id: Mapped[str] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("charging_sessions.session_id"))
    report_seq: Mapped[int]
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(UTCTime)
    received_at: Mapped[datetime] = mapped_column(UTCTime)


class ScenarioScript(Base):
    __tablename__ = "scenario_scripts"
    __table_args__ = (
        Index(
            "uq_running_device_script",
            "device_id",
            unique=True,
            sqlite_where=text("status = 'running'"),
        ),
    )
    script_id: Mapped[str] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    script_name: Mapped[str]
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCTime)
    steps_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    cancel_reason: Mapped[str | None]


class StationState(Base):
    __tablename__ = "station_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    budget_w: Mapped[int] = mapped_column(default=60000)
    revision: Mapped[int] = mapped_column(default=1)
    executing_plan_id: Mapped[str | None] = mapped_column(ForeignKey("power_plans.plan_id"))


class PowerPlan(Base):
    __tablename__ = "power_plans"
    plan_id: Mapped[str] = mapped_column(primary_key=True)
    strategy: Mapped[str]
    budget_w: Mapped[int]
    station_revision: Mapped[int]
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    allocation_json: Mapped[dict] = mapped_column(JSON)
    results_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(UTCTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCTime)


class AlarmRule(Base):
    __tablename__ = "alarm_rules"
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"), primary_key=True)
    reason_code: Mapped[str] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)
    trigger_duration_seconds: Mapped[int] = mapped_column(default=0)
    clear_below_c: Mapped[float] = mapped_column(default=55)
    clear_duration_seconds: Mapped[int] = mapped_column(default=10)
    observation_json: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCTime)


class Alarm(Base):
    __tablename__ = "alarms"
    __table_args__ = (
        Index(
            "uq_active_device_alarm",
            "device_id",
            "reason_code",
            unique=True,
            sqlite_where=text("condition = 'ACTIVE'"),
        ),
    )
    alarm_id: Mapped[str] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    reason_code: Mapped[str]
    condition: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCTime)
    evaluation_state: Mapped[str]
    peak_temperature_c: Mapped[float | None]
    started_at: Mapped[datetime] = mapped_column(UTCTime)
    observed_at: Mapped[datetime] = mapped_column(UTCTime)
    cleared_at: Mapped[datetime | None] = mapped_column(UTCTime)
    rule_json: Mapped[dict] = mapped_column(JSON)
    observation_json: Mapped[dict | None] = mapped_column(JSON)
    evidence_json: Mapped[dict] = mapped_column(JSON)


class AlarmEvent(Base):
    __tablename__ = "alarm_events"
    event_id: Mapped[str] = mapped_column(primary_key=True)
    alarm_id: Mapped[str | None] = mapped_column(ForeignKey("alarms.alarm_id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.device_id"))
    event_type: Mapped[str]
    observed_at: Mapped[datetime] = mapped_column(UTCTime)
    received_at: Mapped[datetime] = mapped_column(UTCTime)
    evidence_json: Mapped[dict] = mapped_column(JSON)


class WorkOrderEvent(Base):
    __tablename__ = "work_order_events"
    event_id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("work_orders.order_id"))
    request_id: Mapped[str] = mapped_column(ForeignKey("operation_requests.request_id"))
    from_status: Mapped[str]
    to_status: Mapped[str]
    note: Mapped[str] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(UTCTime)
    evidence_json: Mapped[dict] = mapped_column(JSON)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("source_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str]
    version: Mapped[str]
    title: Mapped[str]
    category: Mapped[str]
    applicable_model: Mapped[str]
    source_kind: Mapped[str]
    source_url: Mapped[str | None]
    license_note: Mapped[str]
    content_hash: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    current: Mapped[bool]


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[str] = mapped_column(unique=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"))
    heading: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str]


class PatrolSchedule(Base):
    __tablename__ = "patrol_schedules"
    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    interval_seconds: Mapped[int] = mapped_column(default=1800)
    window_minutes: Mapped[int] = mapped_column(default=30)
    next_due_at: Mapped[datetime | None] = mapped_column(UTCTime)
    version: Mapped[int] = mapped_column(default=1)


class PatrolReport(Base):
    __tablename__ = "patrol_reports"
    __table_args__ = (UniqueConstraint("schedule_id", "due_at"),)
    report_id: Mapped[str] = mapped_column(primary_key=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("patrol_schedules.id"))
    due_at: Mapped[datetime | None] = mapped_column(UTCTime)
    request_id: Mapped[str | None] = mapped_column(unique=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.run_id"))
    trigger: Mapped[str]
    status: Mapped[str]
    snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    refs_json: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCTime)
