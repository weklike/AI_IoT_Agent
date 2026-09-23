import json

from backend.app.config import Settings
from eval.run_v2 import CASES, evaluate


def case(identifier):
    return next(
        c for c in map(json.loads, CASES.read_text().splitlines()) if c["case_id"] == identifier
    )


async def test_fixture_evaluation_keeps_actual_api_tools_and_db_evidence(tmp_path):
    result = await evaluate(
        case("B01"), 1, Settings(_env_file=None, app_env="eval", mqtt_enabled=False), tmp_path
    )
    record = json.loads((tmp_path / result["file"]).read_text())
    assert result["automatic_pass"] is True
    assert record["mode"] == "fixture" and record["human_review"] is None
    assert record["before"] == record["after"]
    assert record["runs"][0]["tool_calls"][0]["tool_name"] == "get_fleet_overview"
    assert record["runs"][0]["model_metrics"][0]["usage"] is None


async def test_patrol_timeout_uses_default_three_seconds_and_persists_failure(tmp_path):
    result = await evaluate(
        case("B21"), 1, Settings(_env_file=None, app_env="eval", mqtt_enabled=False), tmp_path
    )
    record = json.loads((tmp_path / result["file"]).read_text())
    assert result["automatic_pass"] is True
    assert record["reports"][0]["status"] == "timed_out"
    assert record["runs"][0]["error_code"] == "TOOL_TIMEOUT"
    assert record["runs"][0]["tool_calls"][0]["duration_ms"] >= 2900
    assert not record["reports"][0]["snapshot_json"]


async def test_two_run_case_records_prelude_without_reusing_its_evidence(tmp_path):
    result = await evaluate(
        case("B22"), 1, Settings(_env_file=None, app_env="eval", mqtt_enabled=False), tmp_path
    )
    record = json.loads((tmp_path / result["file"]).read_text())
    assert len(record["prelude_runs"]) == 1 and len(record["runs"]) == 1
    first, second = record["prelude_runs"][0], record["runs"][0]
    assert first["run_id"] != second["run_id"]
    assert first["tool_calls"][0]["tool_name"] == "search_fault_knowledge"
    assert "[KB:" in second["question"]
    ids = {c["tool_call_id"] for c in first["tool_calls"]}
    assert not any(r["tool_call_id"] in ids for r in second["answer_refs"])
