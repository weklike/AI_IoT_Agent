from uuid import uuid4

import pytest

from backend.app.contracts import ScenarioCommand
from simulator.scenarios import SimulatedDevice, generate_sample


@pytest.mark.parametrize("scenario,bounds", [("normal", (35, 40)), ("overheat", (68, 72))])
def test_deterministic_scenarios(scenario, bounds, fixed_now):
    boot = uuid4()
    sample = generate_sample("CHG-002", boot, 1, scenario, fixed_now)
    repeat = generate_sample("CHG-002", boot, 1, scenario, fixed_now)
    assert sample == repeat
    assert bounds[0] <= sample.temperature_c <= bounds[1]
    assert sample.power_kw == sample.voltage_v * sample.current_a / 1000


def test_offline_retains_control_and_deduplicates(fixed_now):
    device = SimulatedDevice("CHG-002")
    command = ScenarioCommand(command_id=uuid4(), device_id="CHG-002", scenario="offline")
    ack = device.apply_scenario(command, fixed_now)
    assert ack.status == "applied"
    assert device.next_sample(fixed_now) is None
    assert device.apply_scenario(command, fixed_now) == ack
    normal = command.model_copy(update={"command_id": uuid4(), "scenario": "normal"})
    device.apply_scenario(normal, fixed_now)
    assert device.next_sample(fixed_now).seq == 1
    assert device.apply_scenario(command, fixed_now) == ack
    assert device.scenario == "normal"  # repeated old command cannot reapply


def test_independent_boot_and_seq(fixed_now):
    first = SimulatedDevice("CHG-001")
    second = SimulatedDevice("CHG-001")
    assert first.boot_id != second.boot_id
    assert first.next_sample(fixed_now).seq == 1
    assert first.next_sample(fixed_now).seq == 2
    assert second.next_sample(fixed_now).seq == 1


def test_reject_other_device(fixed_now):
    device = SimulatedDevice("CHG-001")
    command = ScenarioCommand(command_id=uuid4(), device_id="CHG-002", scenario="overheat")
    assert device.apply_scenario(command, fixed_now).status == "rejected"
    assert device.scenario == "normal"
