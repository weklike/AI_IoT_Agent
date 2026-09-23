import json

import pytest

from backend.app.agent.tools import schemas, validate_call
from backend.app.errors import DomainError


@pytest.mark.parametrize(
    "name,args",
    [
        ("get_fleet_overview", {"window_minutes": 30}),
        ("get_device_timeline", {"device_id": "CHG-001", "window_minutes": 30}),
        ("get_charging_sessions", {"device_id": "CHG-001", "window_minutes": 10}),
        ("get_work_orders", {"device_id": "CHG-002"}),
        ("search_fault_knowledge", {"query": "功率限制", "device_id": None}),
    ],
)
def test_new_read_tools_reject_server_context_and_are_exposed_without_write_permission(name, args):
    visible = {row["function"]["name"] for row in schemas(False)}
    assert name in visible and "create_work_order" not in visible

    def call(parameters):
        return {"function": {"name": name, "arguments": json.dumps(parameters)}}

    assert validate_call(call(args), False) == args
    for field in ("run_id", "tool_call_id", "allow_work_order"):
        with pytest.raises(DomainError) as error:
            validate_call(call(args | {field: "injected"}), False)
        assert error.value.code == "INVALID_ARGUMENTS"


@pytest.mark.parametrize("window", [True, "10", 0, 61, 1.5])
def test_new_windows_are_strict_and_bounded(window):
    with pytest.raises(DomainError):
        validate_call(
            {
                "function": {
                    "name": "get_fleet_overview",
                    "arguments": json.dumps({"window_minutes": window}),
                }
            },
            False,
        )


@pytest.mark.parametrize("query", ["", "   ", "a" * 301])
def test_search_rejects_blank_and_long_queries(query):
    with pytest.raises(DomainError):
        validate_call(
            {
                "function": {
                    "name": "search_fault_knowledge",
                    "arguments": json.dumps({"query": query, "device_id": None}),
                }
            },
            False,
        )


def test_exact_nine_tools_and_single_write_tool():
    assert len(schemas(True)) == 9
    assert len(schemas(False)) == 8
    assert {row["function"]["name"] for row in schemas(True)} - {
        row["function"]["name"] for row in schemas(False)
    } == {"create_work_order"}
