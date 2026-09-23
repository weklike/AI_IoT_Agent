import json
from uuid import uuid4

import pytest

from backend.app.contracts import parse_telemetry


def payload_v2(valid_payload):
    return {
        **valid_payload,
        "schema_version": 2,
        "session_id": str(uuid4()),
        "session_state": "ACTIVE",
        "requested_power_w": 20000,
        "power_limit_w": 15000,
        "meter_total_wh": 15000,
        "session_energy_wh": 2500,
        "applied_control_generation": 1,
        "current_a": 37.5,
        "power_kw": 15,
    }


def test_dual_json_versions(valid_payload, fixed_now):
    for value in (valid_payload, payload_v2(valid_payload)):
        parsed = parse_telemetry(
            json.dumps(value).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
        )
        assert parsed.schema_version == value["schema_version"]
        assert parsed.model_dump(mode="json")["message_id"] == value["message_id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("power_limit_w", "15000"),
        ("meter_total_wh", True),
        ("session_energy_wh", -1),
        ("requested_power_w", 20001),
        ("applied_control_generation", False),
        ("meter_total_wh", float("nan")),
        ("meter_total_wh", float("inf")),
        ("session_id", "bad"),
        ("extra", 0),
        ("schema_version", True),
        ("schema_version", "2"),
    ],
)
def test_v2_rejects_invalid_fields(valid_payload, fixed_now, field, value):
    payload = payload_v2(valid_payload)
    payload[field] = value
    with pytest.raises(ValueError):
        parse_telemetry(
            json.dumps(payload).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
        )


@pytest.mark.parametrize(
    "overrides",
    [
        dict(session_id=None),
        dict(session_energy_wh=None),
        dict(session_state="IDLE"),
        dict(power_kw=20),
        dict(current_a=50),
    ],
)
def test_v2_cross_field_consistency(valid_payload, fixed_now, overrides):
    payload = {**payload_v2(valid_payload), **overrides}
    with pytest.raises(ValueError):
        parse_telemetry(
            json.dumps(payload).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
        )


def test_control_timestamps_require_iso_text(fixed_now):
    from datetime import timedelta

    from backend.app.charging.contracts import ControlCommand

    good = dict(
        command_id=str(uuid4()),
        device_id="CHG-001",
        generation=1,
        action="stop_session",
        args={"session_id": str(uuid4())},
        issued_at=fixed_now.isoformat(),
        expires_at=(fixed_now + timedelta(seconds=5)).isoformat(),
    )
    assert ControlCommand.model_validate_json(json.dumps(good)).generation == 1
    with pytest.raises(ValueError):
        ControlCommand.model_validate_json(
            json.dumps(
                {
                    **good,
                    "issued_at": fixed_now.timestamp(),
                    "expires_at": fixed_now.timestamp() + 5,
                }
            )
        )


@pytest.mark.parametrize(
    "field",
    [
        "requested_power_w",
        "power_limit_w",
        "meter_total_wh",
        "session_energy_wh",
        "applied_control_generation",
    ],
)
@pytest.mark.parametrize("value", ["1", True, 1.5, float("nan"), float("inf"), -1])
def test_each_v2_numeric_field_is_strict_and_nonnegative(valid_payload, fixed_now, field, value):
    value = {**payload_v2(valid_payload), field: value}
    with pytest.raises(ValueError):
        parse_telemetry(
            json.dumps(value).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
        )


def test_v2_rejects_wrong_topic_unknown_device_then_accepts_good_json(valid_payload, fixed_now):
    value = payload_v2(valid_payload)
    with pytest.raises(ValueError):
        parse_telemetry(
            json.dumps(value).encode(), "charge/v1/devices/CHG-001/telemetry", fixed_now
        )
    with pytest.raises(ValueError):
        parse_telemetry(
            json.dumps({**value, "device_id": "CHG-999"}).encode(),
            "charge/v1/devices/CHG-999/telemetry",
            fixed_now,
        )
    assert (
        parse_telemetry(
            json.dumps(value).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
        ).device_id
        == "CHG-002"
    )
