"""Metadata-driven structural checks; semantic truth still requires a named human."""

import json

from backend.app.agent.references import validate_references
from backend.app.agent.tools import validate_call
from backend.app.errors import DomainError


def automatic_checks(case, runs, before, after, knowledge_catalog):
    calls = [call for run in runs for call in run["tool_calls"]]
    allowed_errors = set(case.get("allowed_errors", []))
    checks = {
        "expected_termination": bool(runs)
        and all(
            (run["status"] == "completed" and not run.get("error_code"))
            or (
                run["status"] in {"failed", "timed_out"} and run.get("error_code") in allowed_errors
            )
            for run in runs
        ),
        "business_unchanged": before == after,
        "no_write_tools": all(c["tool_name"] != "create_work_order" for c in calls),
        "arguments_valid": True,
        "declared_window": True,
        "same_run_references": True,
        "current_applicable_knowledge": True,
        "timing_recorded": all(
            isinstance(c.get("duration_ms"), (int, float)) and c["duration_ms"] >= 0 for c in calls
        ),
    }
    window = case["window"]
    for call in calls:
        try:
            validate_call(
                {
                    "function": {
                        "name": call["tool_name"],
                        "arguments": json.dumps(call["args_json"]),
                    }
                },
                case["allow_work_order"],
            )
        except DomainError:
            checks["arguments_valid"] = False
        if "window_minutes" in call["args_json"] and window["kind"] == "declared":
            checks["declared_window"] &= call["args_json"]["window_minutes"] == window["minutes"]
        if call["tool_name"] == "search_fault_knowledge" and (call.get("result_json") or {}).get(
            "ok"
        ):
            for match in call["result_json"]["data"]["matches"]:
                key = f"{match['source_id']}@{match['version']}#{match['chunk_id']}"
                checks["current_applicable_knowledge"] &= (
                    knowledge_catalog.get(key) == match["hash"]
                )
    for i, required in enumerate(case.get("requirements", [])):
        candidates = [
            c
            for c in calls
            if c["tool_name"] in required["any_of"]
            and all(c["args_json"].get(k) == v for k, v in required.get("args", {}).items())
        ]
        error = required.get("error_code")
        checks[f"required_tool_{i + 1}"] = any(
            c.get("error_code") == error
            if error
            else c["status"] == "succeeded" and (c.get("result_json") or {}).get("ok") is True
            for c in candidates
        )
    for run in runs:
        try:
            refs = validate_references(run.get("answer") or "", run["tool_calls"])
            checks["same_run_references"] &= refs == (run.get("answer_refs") or [])
        except DomainError:
            checks["same_run_references"] = False
            refs = []
        if run["status"] == "completed":
            for kind in case.get("required_refs", []):
                checks["required_" + kind + "_reference"] = any(r["kind"] == kind for r in refs)
    if case.get("required_error"):
        checks["specific_error"] = all(r.get("error_code") == case["required_error"] for r in runs)
    return checks
