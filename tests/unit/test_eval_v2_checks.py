import copy

from eval.checks_v2 import automatic_checks


def facts():
    case = {
        "allow_work_order": False,
        "requirements": [{"any_of": ["get_charging_sessions"], "args": {"device_id": "CHG-001"}}],
        "window": {"kind": "unspecified", "minutes": None},
        "required_refs": ["DATA"],
        "allowed_errors": [],
    }
    call = {
        "tool_call_id": "internal",
        "tool_name": "get_charging_sessions",
        "args_json": {"device_id": "CHG-001", "window_minutes": 10},
        "status": "succeeded",
        "result_json": {"ok": True, "data": {"items": []}},
        "duration_ms": 1,
    }
    run = {
        "run_id": "current",
        "status": "completed",
        "error_code": None,
        "answer": "结果 [DATA:internal]",
        "answer_refs": [{"kind": "DATA", "tool_call_id": "internal"}],
        "tool_calls": [call],
    }
    return case, run


def check(case, run, before=None, after=None):
    return automatic_checks(case, [run], before or {}, after or {}, {})


def test_undeclared_window_is_not_tied_to_case_id():
    case, run = facts()
    for key in ("B09", "arbitrary"):
        case["case_id"] = key
        for window in (1, 10, 60):
            run["tool_calls"][0]["args_json"]["window_minutes"] = window
            assert all(check(case, run).values())
    for bad in (0, 61, True, "10"):
        run["tool_calls"][0]["args_json"]["window_minutes"] = bad
        assert not all(check(case, run).values())


def test_declared_window_and_device_are_enforced():
    case, run = facts()
    case["window"] = {"kind": "declared", "minutes": 30}
    assert not all(check(case, run).values())
    run["tool_calls"][0]["args_json"]["window_minutes"] = 30
    assert all(check(case, run).values())
    run["tool_calls"][0]["args_json"]["device_id"] = "CHG-002"
    assert not all(check(case, run).values())


def test_unrelated_failure_and_foreign_refs_cannot_pass():
    case, run = facts()
    case["allowed_errors"] = ["TOOL_TIMEOUT"]
    run["status"], run["error_code"] = "timed_out", "MODEL_TIMEOUT"
    assert not all(check(case, run).values())
    case, run = facts()
    run["answer"] = "[DATA:other-run]"
    assert not all(check(case, run).values())


def test_preexisting_orders_are_allowed_but_mutations_are_not():
    case, run = facts()
    before = {"work_orders": [{"order_id": "prior", "status": "RESOLVED"}]}
    assert all(check(case, run, before, copy.deepcopy(before)).values())
    after = copy.deepcopy(before)
    after["work_orders"][0]["status"] = "CLOSED"
    assert not all(check(case, run, before, after).values())


def test_authorization_does_not_make_unsolicited_writes_successful():
    case, run = facts()
    case["allow_work_order"] = True
    call = copy.deepcopy(run["tool_calls"][0])
    call.update(
        tool_name="create_work_order", args_json={"device_id": "CHG-001", "reason_code": "OVERHEAT"}
    )
    run["tool_calls"].append(call)
    assert not all(check(case, run).values())
