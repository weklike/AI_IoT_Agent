from datetime import timedelta
from uuid import uuid4


def test_retry_schedule_ack_matching_and_expired_evidence(tmp_path, fixed_now):
    from backend.app.charging.contracts import ControlCommand, SessionAck
    from simulator.charging import ChargingDevice
    from simulator.reports import ReportDelivery

    device = ChargingDevice("CHG-001", tmp_path / "state.json", fixed_now, monotonic_ns=0)
    device.apply(
        ControlCommand(
            command_id=uuid4(),
            device_id="CHG-001",
            generation=1,
            action="start_session",
            args={"session_id": str(uuid4()), "requested_power_w": 20000},
            issued_at=fixed_now,
            expires_at=fixed_now + timedelta(seconds=5),
        ),
        fixed_now,
        0,
    )
    delivery = ReportDelivery(device)
    assert len(delivery.due(fixed_now)) == 1
    assert delivery.due(fixed_now + timedelta(milliseconds=999)) == []
    assert len(delivery.due(fixed_now + timedelta(seconds=1))) == 1
    assert delivery.due(fixed_now + timedelta(seconds=2)) == []
    assert len(delivery.due(fixed_now + timedelta(seconds=3))) == 1
    assert len(delivery.due(fixed_now + timedelta(seconds=7))) == 1
    assert delivery.due(fixed_now + timedelta(seconds=8)) == []
    assert delivery.due(fixed_now + timedelta(days=1)) == []
    assert device.state["pending_reports"][0]["delivery_failed"]
    report = device.state["pending_reports"][0]["payload"]
    delivery.ack(
        SessionAck(
            report_id=uuid4(), session_id=report["session_id"], report_seq=1, status="stored"
        ),
        fixed_now,
    )
    assert len(device.state["pending_reports"]) == 1
    delivery.ack(
        SessionAck(
            report_id=report["report_id"],
            session_id=report["session_id"],
            report_seq=1,
            status="stored",
        ),
        fixed_now,
    )
    assert device.state["pending_reports"] == []


def test_pending_reports_bounded_and_backlog_refuses_start_but_allows_stop(tmp_path, fixed_now):
    from datetime import timedelta
    from uuid import uuid4

    from backend.app.charging.contracts import ControlCommand
    from simulator.charging import ChargingDevice

    device = ChargingDevice("CHG-001", tmp_path / "state.json", fixed_now, monotonic_ns=0)
    generation = 0

    def apply(action, args):
        nonlocal generation
        generation += 1
        return device.apply(
            ControlCommand(
                command_id=uuid4(),
                device_id="CHG-001",
                generation=generation,
                action=action,
                args=args,
                issued_at=fixed_now,
                expires_at=fixed_now + timedelta(seconds=5),
            ),
            fixed_now,
            0,
        )

    for _ in range(100):
        session_id = str(uuid4())
        assert (
            apply("start_session", {"session_id": session_id, "requested_power_w": 20000}).status
            == "applied"
        )
        for _ in range(4):
            device.report(fixed_now, 0)
        assert apply("stop_session", {"session_id": session_id}).status == "applied"
    assert len(device.state["pending_reports"]) == 300
    assert (
        apply("start_session", {"session_id": str(uuid4()), "requested_power_w": 20000}).error_code
        == "REPORT_BACKLOG_FULL"
    )
    assert len(device.state["pending_reports"]) == 300


def test_checkpoint_replace_failure_keeps_previous_file(tmp_path, monkeypatch):
    import os

    import pytest

    from simulator.state_store import load_state, save_state

    path = tmp_path / "state.json"
    save_state(path, {"version": 1, "meter_total_wh": 100})

    def fail(*args):
        raise OSError("injected disk failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        save_state(path, {"version": 1, "meter_total_wh": 200})
    assert load_state(path)["meter_total_wh"] == 100
    assert list(tmp_path.iterdir()) == [path]


def test_delivery_metadata_does_not_advance_meter_checkpoint_time(tmp_path, fixed_now):
    from datetime import timedelta

    from simulator.charging import ChargingDevice
    from simulator.reports import ReportDelivery

    device = ChargingDevice("CHG-001", tmp_path / "state.json", fixed_now, monotonic_ns=0)
    measured = fixed_now + timedelta(seconds=2)
    device.checkpoint(measured, 2_000_000_000)
    device.state["pending_reports"] = [
        {
            "payload": {"report_id": "retained-evidence"},
            "attempts": 0,
            "first_sent_at": measured.isoformat(),
            "next_due_at": measured.isoformat(),
            "delivery_failed": False,
        }
    ]
    ReportDelivery(device).due(fixed_now + timedelta(seconds=3))
    assert device.state["last_checkpoint"] == measured.isoformat()
