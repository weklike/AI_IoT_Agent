import json
from datetime import timedelta

import pytest
from pydantic import ValidationError

from backend.app.contracts import TelemetryMessage, parse_telemetry


def test_valid_json_strings_parse(valid_payload, fixed_now):
    sample = parse_telemetry(
        json.dumps(valid_payload).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
    )
    assert sample.ts == fixed_now
    assert str(sample.message_id) == valid_payload["message_id"]
    assert sample.temperature_c == 71.0


@pytest.mark.parametrize("field", ["temperature_c", "voltage_v", "current_a", "power_kw"])
@pytest.mark.parametrize("value", ["42", True, False, float("nan"), float("inf"), -float("inf")])
def test_strict_finite_numbers(field, value, valid_payload):
    valid_payload[field] = value
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(valid_payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("seq", 0),
        ("seq", True),
        ("seq", "1"),
        ("seq", 1.5),
        ("temperature_c", 121),
        ("temperature_c", -21),
        ("voltage_v", 1001),
        ("current_a", -1),
        ("power_kw", 301),
        ("operating_state", "running"),
        ("device_id", "CHG-999"),
        ("ts", "2026-09-22T08:10:00"),
        ("message_id", "bad"),
        ("extra", 1),
    ],
)
def test_invalid_fields(field, value, valid_payload):
    valid_payload[field] = value
    with pytest.raises(ValidationError):
        TelemetryMessage.model_validate(valid_payload)


@pytest.mark.parametrize(
    "offset,accepted", [(5, True), (5.001, False), (-86400, True), (-86400.001, False)]
)
def test_time_boundaries(offset, accepted, valid_payload, fixed_now):
    valid_payload["ts"] = (fixed_now + timedelta(seconds=offset)).isoformat()
    if accepted:
        parse_telemetry(
            json.dumps(valid_payload).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
        )
    else:
        with pytest.raises(ValueError):
            parse_telemetry(
                json.dumps(valid_payload).encode(), "charge/v1/devices/CHG-002/telemetry", fixed_now
            )


@pytest.mark.parametrize(
    "topic", ["charge/v1/devices/CHG-001/telemetry", "charge/v1/devices/CHG-002/other"]
)
def test_topic_must_match(topic, valid_payload, fixed_now):
    with pytest.raises(ValueError):
        parse_telemetry(json.dumps(valid_payload).encode(), topic, fixed_now)


@pytest.mark.parametrize("payload", [b"{", b"{}", b" " * 8193])
def test_invalid_payload(payload, fixed_now):
    with pytest.raises(ValueError):
        parse_telemetry(payload, "charge/v1/devices/CHG-002/telemetry", fixed_now)
