from copy import deepcopy
from datetime import timedelta

from scripts.power_protection_v2 import assess_plan
from tests.support.fixtures import T0


def evidence():
    old = {f"CHG-00{i}": {"power_limit_w": 15000} for i in (1, 2, 3)}
    targets = {"CHG-001": 20000, "CHG-002": 20000, "CHG-003": 5000}
    commands = {}
    for device, target in targets.items():
        lower = target < 15000
        commands[device] = {
            "command_id": device,
            "device_id": device,
            "generation": 2,
            "status": "applied",
            "verification_status": "verified",
            "args_json": {"power_limit_w": target},
            "issued_at": (T0 + timedelta(seconds=1 if lower else 3)).isoformat(),
            "verification_json": {
                "checked_at": (T0 + timedelta(seconds=2 if lower else 4)).isoformat(),
                "message_id": device,
            },
        }
    plan = {
        "status": "VERIFIED",
        "budget_w": 45000,
        "snapshot_json": {"fingerprint": old, "confirmed_budget_w": 45000},
        "allocation_json": targets,
        "results_json": {d: {"worst_case_w": 45000, "protection_budget_w": 45000} for d in targets},
    }
    states = {
        d: {"power_limit_w": t, "data_fresh": True, "applied_control_generation": 2}
        for d, t in targets.items()
    }
    return plan, commands, states


def test_reconstructs_actual_upper_bounds_and_order():
    plan, commands, states = evidence()
    assert all(assess_plan(plan, commands, states, 5)["checks"].values())
    commands["CHG-001"]["issued_at"] = (T0 + timedelta(seconds=1.5)).isoformat()
    result = assess_plan(plan, commands, states, 5)
    assert result["checks"]["decreases_verified_before_increases"] is False
    assert result["checks"]["upper_bound_safe"] is False


def test_unknown_result_cannot_be_called_verified():
    plan, commands, states = evidence()
    altered = deepcopy(commands)
    altered["CHG-003"].update(
        status="timed_out", verification_status="pending", verification_json=None
    )
    assert not all(assess_plan(plan, altered, states, 5)["checks"].values())
    states["CHG-003"]["power_limit_w"] = 15000
    assert not all(assess_plan(plan, commands, states, 5)["checks"].values())
    assert not all(assess_plan(plan, commands, states, 36)["checks"].values())
