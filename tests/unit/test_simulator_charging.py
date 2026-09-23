def test_energy_integrates_fractional_wh_without_sample_rounding():
    from simulator.charging import EnergyMeter

    meter = EnergyMeter(total_wh=10000)
    for _ in range(300):
        meter.advance(power_w=20000, elapsed_ns=2_000_000_000)
    assert meter.total_wh == 13333
    meter.advance(power_w=15000, elapsed_ns=600_000_000_000)
    assert meter.total_wh == 15833
    before = meter.total_wh
    meter.advance(power_w=15000, elapsed_ns=0)
    assert meter.total_wh == before


def test_persisted_meter_restart_interrupts_without_downtime_energy(tmp_path, fixed_now):
    from datetime import timedelta
    from uuid import uuid4

    from backend.app.charging.contracts import ControlCommand
    from simulator.charging import ChargingDevice

    path = tmp_path / "CHG-001.json"
    device = ChargingDevice("CHG-001", path, fixed_now, monotonic_ns=0)
    session_id = str(uuid4())

    def command(generation, action, args):
        return ControlCommand(
            command_id=uuid4(),
            device_id="CHG-001",
            generation=generation,
            action=action,
            args=args,
            issued_at=fixed_now,
            expires_at=fixed_now + timedelta(seconds=5),
        )

    start = command(1, "start_session", {"session_id": session_id, "requested_power_w": 20000})
    assert device.apply(start, fixed_now, 0).status == "applied"
    assert device.power_limit_w == 0
    assert (
        device.apply(command(2, "set_power_limit", {"power_limit_w": 20000}), fixed_now, 0).status
        == "applied"
    )
    device.checkpoint(fixed_now + timedelta(seconds=600), 600_000_000_000)
    assert device.meter.total_wh == 3333
    restarted = ChargingDevice("CHG-001", path, fixed_now + timedelta(seconds=900), monotonic_ns=0)
    assert restarted.meter.total_wh == 3333
    assert restarted.state["session"]["status"] == "INTERRUPTED"
    assert restarted.state["session"]["end_reason"] == "SIMULATOR_RESTART"
    assert restarted.state["session"]["meter_quality"] == "checkpoint"
    assert restarted.apply(start, fixed_now + timedelta(seconds=900), 0).status == "applied"
    assert restarted.state["session"]["status"] == "INTERRUPTED"
    assert restarted.power_limit_w == 0


def test_rejected_high_generation_fences_later_lower_command(tmp_path, fixed_now):
    from datetime import timedelta
    from uuid import uuid4

    from backend.app.charging.contracts import ControlCommand
    from simulator.charging import ChargingDevice

    device = ChargingDevice("CHG-001", tmp_path / "state.json", fixed_now, monotonic_ns=0)

    def command(generation, action, args):
        return ControlCommand(
            command_id=uuid4(),
            device_id="CHG-001",
            generation=generation,
            action=action,
            args=args,
            issued_at=fixed_now,
            expires_at=fixed_now + timedelta(seconds=5),
        )

    assert (
        device.apply(command(5, "stop_session", {"session_id": str(uuid4())}), fixed_now, 0).status
        == "rejected"
    )
    result = device.apply(
        command(4, "start_session", {"session_id": str(uuid4()), "requested_power_w": 20000}),
        fixed_now,
        0,
    )
    assert result.error_code == "OLD_GENERATION"
    assert not device.active


def test_ten_duplicate_controls_conflict_old_generation_and_expiry(tmp_path, fixed_now):
    from datetime import timedelta
    from uuid import uuid4

    from backend.app.charging.contracts import ControlCommand
    from simulator.charging import ChargingDevice

    device = ChargingDevice("CHG-001", tmp_path / "state.json", fixed_now, monotonic_ns=0)
    session_id = str(uuid4())

    def command(generation, action, args, issued=fixed_now):
        return ControlCommand(
            command_id=uuid4(),
            device_id="CHG-001",
            generation=generation,
            action=action,
            args=args,
            issued_at=issued,
            expires_at=issued + timedelta(seconds=5),
        )

    start = command(1, "start_session", {"session_id": session_id, "requested_power_w": 20000})
    accepted = device.apply(start, fixed_now, 0)
    for _ in range(10):
        assert device.apply(start, fixed_now, 0) == accepted
    assert device.state["session"]["session_id"] == session_id
    assert len(device.state["pending_reports"]) == 1
    assert device.state["session"]["report_seq"] == 1
    conflict = ControlCommand.model_validate(
        {**start.model_dump(), "args": {"session_id": session_id, "requested_power_w": 10000}}
    )
    assert device.apply(conflict, fixed_now, 0).error_code == "COMMAND_CONFLICT"
    assert device.apply(start, fixed_now, 0) == accepted
    limit = command(2, "set_power_limit", {"power_limit_w": 20000})
    applied = device.apply(limit, fixed_now, 0)
    device.checkpoint(fixed_now + timedelta(seconds=2), 2_000_000_000)
    energy = device.meter.total_wh
    for _ in range(10):
        assert device.apply(limit, fixed_now + timedelta(seconds=2), 2_000_000_000) == applied
        assert device.meter.total_wh == energy
    assert (
        device.apply(
            command(1, "set_power_limit", {"power_limit_w": 10000}),
            fixed_now + timedelta(seconds=2),
            2_000_000_000,
        ).error_code
        == "OLD_GENERATION"
    )
    expired = command(
        3, "set_power_limit", {"power_limit_w": 10000}, fixed_now - timedelta(seconds=6)
    )
    assert (
        device.apply(expired, fixed_now + timedelta(seconds=2), 2_000_000_000).error_code
        == "COMMAND_EXPIRED"
    )
    assert device.state["session"]["session_id"] == session_id and device.power_limit_w == 20000
