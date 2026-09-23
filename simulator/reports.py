"""Explicit application-ACK delivery policy, separate from MQTT PUBACK."""

from datetime import datetime, timedelta

from backend.app.charging.contracts import SessionAck
from simulator.charging import ChargingDevice


class ReportDelivery:
    def __init__(
        self,
        device: ChargingDevice,
        *,
        expiry_seconds: float = 86400,
        retry_seconds: tuple[float, ...] = (1, 2, 4, 30),
    ):
        self.device, self.expiry_seconds, self.retry_seconds = device, expiry_seconds, retry_seconds

    def due(self, now: datetime) -> list[dict]:
        result = []
        changed = False
        for item in self.device.state["pending_reports"]:
            if item["delivery_failed"]:
                continue
            if (
                now - datetime.fromisoformat(item["first_sent_at"])
            ).total_seconds() >= self.expiry_seconds:
                item["delivery_failed"] = True
                changed = True
                continue
            if now < datetime.fromisoformat(item["next_due_at"]):
                continue
            delay = self.retry_seconds[min(item["attempts"], len(self.retry_seconds) - 1)]
            changed = True
            item["attempts"] += 1
            item["next_due_at"] = (now + timedelta(seconds=delay)).isoformat()
            result.append(item["payload"])
        if changed:
            self.device._save(now, measured=False)
        return result

    def ack(self, ack: SessionAck, now: datetime) -> None:
        for item in list(self.device.state["pending_reports"]):
            payload = item["payload"]
            if (payload["report_id"], payload["session_id"], payload["report_seq"]) != (
                str(ack.report_id),
                str(ack.session_id),
                ack.report_seq,
            ):
                continue
            if ack.status == "stored":
                self.device.state["pending_reports"].remove(item)
            else:
                item["delivery_failed"] = True
                item["rejection_status"] = ack.status
            self.device._save(now, measured=False)
            break
