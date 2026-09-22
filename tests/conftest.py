from datetime import UTC, datetime

import pytest


@pytest.fixture
def fixed_now():
    return datetime(2026, 9, 22, 8, 10, tzinfo=UTC)


@pytest.fixture
def valid_payload(fixed_now):
    return {
        "schema_version": 1,
        "device_id": "CHG-002",
        "message_id": "bb7ce354-0569-4bcb-82de-233380fbba31",
        "boot_id": "ee456e0c-cd91-4fe0-83f1-a63dfc076f6a",
        "seq": 17,
        "ts": fixed_now.isoformat(),
        "temperature_c": 71.0,
        "voltage_v": 400.0,
        "current_a": 50.0,
        "power_kw": 20.0,
        "operating_state": "charging",
    }
