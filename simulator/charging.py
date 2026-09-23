"""Deterministic integer metering; callers supply real monotonic elapsed nanoseconds."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.charging.contracts import ControlAck, ControlCommand
from backend.app.contracts import DeviceID


@dataclass
class EnergyMeter:
    total_wh: int = 0
    remainder_wns: int = 0

    def advance(self, *, power_w: int, elapsed_ns: int) -> None:
        if type(power_w) is not int or not 0 <= power_w <= 20000:
            raise ValueError("Power must be an integer within the device rating")
        if type(elapsed_ns) is not int or elapsed_ns < 0:
            raise ValueError("Elapsed time must be nonnegative integer nanoseconds")
        whole, self.remainder_wns = divmod(
            self.remainder_wns + power_w * elapsed_ns, 3_600_000_000_000
        )
        self.total_wh += whole


class ChargingDevice:
    """Per-device serial command state. Persist before returning any applied ACK."""

    def __init__(self, device_id: DeviceID, path: Path, now: datetime, *, monotonic_ns: int):
        from simulator.state_store import load_state

        self.device_id, self.path = device_id, path
        self.state = load_state(path) or {
            "version": 1,
            "device_id": device_id,
            "meter_total_wh": 0,
            "remainder_wns": 0,
            "generation": 0,
            "commands": [],
            "session": None,
            "pending_reports": [],
            "power_limit_w": 0,
            "last_checkpoint": now.isoformat(),
        }
        if self.state["device_id"] != device_id:
            raise ValueError("Checkpoint belongs to another device")
        self.state.setdefault("highest_generation", self.state["generation"])
        self.meter = EnergyMeter(self.state["meter_total_wh"], self.state["remainder_wns"])
        self.last_ns = monotonic_ns
        if self.active:
            # Recover only the last persisted measurement, never integrate process downtime.
            from datetime import datetime

            ended = datetime.fromisoformat(self.state["last_checkpoint"])
            self._finish(ended, "SIMULATOR_RESTART", "checkpoint")
            self._report(now)
        self._save(now)

    @property
    def active(self) -> bool:
        return self.state["session"] is not None and self.state["session"]["status"] == "ACTIVE"

    @property
    def power_limit_w(self) -> int:
        return self.state["power_limit_w"]

    @property
    def actual_power_w(self) -> int:
        return (
            min(self.power_limit_w, self.state["session"]["requested_power_w"])
            if self.active
            else 0
        )

    def _advance(self, monotonic_ns: int) -> None:
        self.meter.advance(power_w=self.actual_power_w, elapsed_ns=monotonic_ns - self.last_ns)
        self.last_ns = monotonic_ns

    def _save(self, now: datetime, *, measured: bool = True) -> None:
        from simulator.state_store import save_state

        self.state.update(
            meter_total_wh=self.meter.total_wh,
            remainder_wns=self.meter.remainder_wns,
        )
        if measured:
            self.state["last_checkpoint"] = now.isoformat()
        save_state(self.path, self.state)

    def checkpoint(self, now: datetime, monotonic_ns: int) -> None:
        self._advance(monotonic_ns)
        self._save(now)

    def _finish(self, now: datetime, reason: str, quality: str = "exact") -> None:
        self.state["power_limit_w"] = 0
        self.state["session"].update(
            status="COMPLETED" if reason == "USER_STOP" else "INTERRUPTED",
            ended_at=now.isoformat(),
            end_reason=reason,
            meter_quality=quality,
        )

    def _report(self, now: datetime) -> None:
        from uuid import uuid4

        session = self.state["session"]
        if session is None:
            return
        if session["status"] == "ACTIVE" and any(
            item["delivery_failed"] and item["payload"]["session_id"] == session["session_id"]
            for item in self.state["pending_reports"]
        ):
            return
        session["report_seq"] += 1
        payload = {
            key: session[key]
            for key in (
                "session_id",
                "report_seq",
                "started_at",
                "ended_at",
                "status",
                "start_meter_wh",
                "end_reason",
                "meter_quality",
            )
        }
        payload.update(
            report_id=str(uuid4()),
            device_id=self.device_id,
            observed_at=now.isoformat(),
            end_meter_wh=self.meter.total_wh,
            energy_wh=self.meter.total_wh - session["start_meter_wh"],
        )
        # Keep start, latest intermediate and final; never evict another session's evidence.
        pending = self.state["pending_reports"]
        if session["status"] == "ACTIVE" and session["report_seq"] > 1:
            pending[:] = [
                item
                for item in pending
                if not (
                    item["payload"]["session_id"] == session["session_id"]
                    and item["payload"]["status"] == "ACTIVE"
                    and item["payload"]["report_seq"] > 1
                    and not item.get("delivery_failed")
                )
            ]
        pending.append(
            {
                "payload": payload,
                "attempts": 0,
                "next_due_at": now.isoformat(),
                "first_sent_at": now.isoformat(),
                "delivery_failed": False,
            }
        )

    def report(self, now: datetime, monotonic_ns: int) -> None:
        self._advance(monotonic_ns)
        self._report(now)
        self._save(now)

    def apply(self, command: ControlCommand, now: datetime, monotonic_ns: int) -> ControlAck:
        import hashlib
        import json

        from backend.app.charging.contracts import ControlAck

        self._advance(monotonic_ns)
        digest = hashlib.sha256(command.model_dump_json().encode()).hexdigest()
        for cached in self.state["commands"]:
            if cached["command_id"] == str(command.command_id):
                if cached["digest"] == digest:
                    self._save(now)
                    return ControlAck.model_validate(cached["ack"])
                error = "COMMAND_CONFLICT"
                break
        else:
            error = None
        if error is None:
            if command.device_id != self.device_id:
                error = "DEVICE_MISMATCH"
            elif now >= command.expires_at or now < command.issued_at:
                error = "COMMAND_EXPIRED"
            elif command.generation <= self.state["highest_generation"]:
                error = "OLD_GENERATION"
            else:
                self.state["highest_generation"] = command.generation
        if error is None:
            if command.action == "start_session":
                pending_sessions = {
                    item["payload"]["session_id"] for item in self.state["pending_reports"]
                }
                if self.active:
                    error = "SESSION_CONFLICT"
                elif len(pending_sessions) >= 100:
                    error = "REPORT_BACKLOG_FULL"
                else:
                    self.state["session"] = dict(
                        command.args,
                        status="ACTIVE",
                        started_at=now.isoformat(),
                        ended_at=None,
                        start_meter_wh=self.meter.total_wh,
                        end_reason=None,
                        meter_quality="exact",
                        report_seq=0,
                    )
                    self.state["power_limit_w"] = 0
                    self._report(now)
            elif command.action == "stop_session":
                if (
                    not self.active
                    or command.args["session_id"] != self.state["session"]["session_id"]
                ):
                    error = "SESSION_CONFLICT"
                else:
                    self._finish(now, "USER_STOP")
                    self._report(now)
            elif not self.active:
                error = "SESSION_CONFLICT"
            else:
                self.state["power_limit_w"] = command.args["power_limit_w"]
        if error is None:
            self.state["generation"] = command.generation
        ack = ControlAck(
            **command.model_dump(),
            applied_at=now,
            status="rejected" if error else "applied",
            error_code=error,
            actual_state=self.telemetry_fields(),
        )
        # Preserve original result when an attacker reuses its ID with other content.
        if error != "COMMAND_CONFLICT":
            self.state["commands"].append(
                dict(
                    command_id=str(command.command_id),
                    digest=digest,
                    ack=json.loads(ack.model_dump_json()),
                )
            )
            self.state["commands"] = self.state["commands"][-100:]
        self._save(now)
        return ack

    def telemetry_fields(self) -> dict[str, Any]:
        session = self.state["session"] if self.active else None
        return dict(
            session_id=session["session_id"] if session else None,
            session_state="ACTIVE" if session else "IDLE",
            requested_power_w=session["requested_power_w"] if session else 0,
            power_limit_w=self.power_limit_w if session else 0,
            meter_total_wh=self.meter.total_wh,
            session_energy_wh=self.meter.total_wh - session["start_meter_wh"] if session else None,
            applied_control_generation=self.state["generation"],
        )
