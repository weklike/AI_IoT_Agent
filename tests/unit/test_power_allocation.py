import pytest


def test_equal_water_filling_and_stable_100w_remainder():
    from backend.app.power.allocation import allocate_power

    demands = {"CHG-001": 20000, "CHG-002": 20000, "CHG-003": 20000}
    assert allocate_power(45000, demands, "equal", None) == dict.fromkeys(demands, 15000)
    assert allocate_power(45100, demands, "equal", None) == {
        "CHG-001": 15100,
        "CHG-002": 15000,
        "CHG-003": 15000,
    }
    assert allocate_power(45000, {**demands, "CHG-001": 10000}, "equal", None) == {
        "CHG-001": 10000,
        "CHG-002": 17500,
        "CHG-003": 17500,
    }
    assert allocate_power(60000, dict.fromkeys(demands, 10000), "equal", None) == dict.fromkeys(
        demands, 10000
    )


def test_priority_caps_and_zero_budget():
    from backend.app.power.allocation import allocate_power

    demands = dict.fromkeys(("CHG-001", "CHG-002", "CHG-003"), 20000)
    order = ["CHG-002", "CHG-001", "CHG-003"]
    assert allocate_power(45000, demands, "priority", order) == {
        "CHG-001": 20000,
        "CHG-002": 20000,
        "CHG-003": 5000,
    }
    assert allocate_power(0, demands, "equal", None) == dict.fromkeys(demands, 0)
    assert allocate_power(60000, dict.fromkeys(demands, 0), "equal", None) == dict.fromkeys(
        demands, 0
    )


@pytest.mark.parametrize(
    "budget,demands,strategy,priority",
    [
        (True, {"CHG-001": 1000}, "equal", None),
        (45101, {"CHG-001": 1000}, "equal", None),
        (60100, {"CHG-001": 1000}, "equal", None),
        (45000, {"CHG-001": True}, "equal", None),
        (45000, {"CHG-001": 20100}, "equal", None),
        (45000, {"CHG-001": 1000}, "priority", ["CHG-001"] * 3),
    ],
)
def test_reject_invalid_power_inputs(budget, demands, strategy, priority):
    from backend.app.power.allocation import allocate_power

    with pytest.raises(ValueError):
        allocate_power(budget, demands, strategy, priority)
