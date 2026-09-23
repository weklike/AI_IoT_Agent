from datetime import timedelta
from uuid import uuid4

from backend.app.charging.contracts import ControlCommand
from simulator.charging import ChargingDevice


def test_stopped_meter_does_not_advance_and_new_session_uses_its_own_baseline(tmp_path, fixed_now):
    device = ChargingDevice("CHG-001", tmp_path / "state.json", fixed_now, monotonic_ns=0)

    def apply(generation, action, args, second):
        now = fixed_now + timedelta(seconds=second)
        command = ControlCommand(
            command_id=uuid4(),
            device_id="CHG-001",
            generation=generation,
            action=action,
            args=args,
            issued_at=now,
            expires_at=now + timedelta(seconds=5),
        )
        assert device.apply(command, now, second * 1_000_000_000).status == "applied"

    first, second = str(uuid4()), str(uuid4())
    apply(1, "start_session", {"session_id": first, "requested_power_w": 20000}, 0)
    apply(2, "set_power_limit", {"power_limit_w": 20000}, 0)
    apply(3, "stop_session", {"session_id": first}, 600)
    assert device.meter.total_wh == 3333
    assert device.power_limit_w == 0
    device.checkpoint(fixed_now + timedelta(seconds=1200), 1200_000_000_000)
    assert device.meter.total_wh == 3333
    apply(4, "start_session", {"session_id": second, "requested_power_w": 10000}, 1200)
    assert device.power_limit_w == 0
    apply(5, "set_power_limit", {"power_limit_w": 10000}, 1200)
    device.checkpoint(fixed_now + timedelta(seconds=1800), 1800_000_000_000)
    fields = device.telemetry_fields()
    assert fields["session_id"] == second
    assert fields["session_energy_wh"] == 1667
    assert device.meter.total_wh == 5000
    old = [
        r["payload"]
        for r in device.state["pending_reports"]
        if r["payload"]["session_id"] == first and r["payload"]["status"] == "COMPLETED"
    ]
    assert len(old) == 1 and old[0]["energy_wh"] == 3333
