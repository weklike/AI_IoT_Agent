"""Integer, bounded allocation for the three simulated charging devices."""

from collections.abc import Mapping, Sequence
from typing import Literal

from backend.app.contracts import DEVICE_IDS


def allocate_power(
    budget_w: int,
    demands_w: Mapping[str, int],
    strategy: Literal["equal", "priority"],
    device_priority: Sequence[str] | None,
) -> dict[str, int]:
    if type(budget_w) is not int or not 0 <= budget_w <= 60000 or budget_w % 100:
        raise ValueError("Budget must be 0—60000 W in 100 W units")
    if strategy not in {"equal", "priority"} or set(demands_w) - set(DEVICE_IDS):
        raise ValueError("Unknown strategy or device")
    if any(
        type(value) is not int or not 0 <= value <= 20000 or value % 100
        for value in demands_w.values()
    ):
        raise ValueError("Device demand must be 0—20000 W in 100 W units")
    if device_priority is not None and (
        len(device_priority) != 3 or set(device_priority) != set(DEVICE_IDS)
    ):
        raise ValueError("Priority must name all three devices exactly once")
    if strategy == "priority" and device_priority is None:
        raise ValueError("Priority strategy requires device order")
    result = dict.fromkeys(DEVICE_IDS, 0)
    remaining = budget_w
    if strategy == "priority":
        for device in device_priority:
            result[device] = min(demands_w.get(device, 0), remaining)
            remaining -= result[device]
    else:
        # Each pass allocates one 100 W share; capped devices leave the active set.
        # Ascending IDs deterministically receive any final indivisible shares.
        while remaining:
            eligible = [
                device for device in DEVICE_IDS if result[device] < demands_w.get(device, 0)
            ]
            if not eligible:
                break
            for device in eligible:
                if remaining == 0:
                    break
                result[device] += 100
                remaining -= 100
    return result
