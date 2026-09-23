import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "evaluation_entry", Path(__file__).parents[2] / "eval/run.py"
)
EVAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVAL)


def evidence(tmp_path, mode="real", passes=60, critical=None):
    entries, reviews = [], []
    index = 0
    for case in range(1, 21):
        for repeat in range(1, 4):
            path = tmp_path / f"A{case:02}-{repeat}.json"
            path.write_text(
                json.dumps(
                    {
                        "case": {"category": str((case - 1) // 4)},
                        "automatic_pass": True,
                        "total_seconds": 1.0,
                    }
                )
            )
            digest = EVAL.sha(path.read_bytes())
            entries.append(
                {"case_id": f"A{case:02}", "repeat": repeat, "file": path.name, "sha256": digest}
            )
            # Synthetic reviewers belong only to isolated summarizer unit-test fixtures.
            reviews.append(
                {
                    "case_id": f"A{case:02}",
                    "repeat": repeat,
                    "reviewer": "SYNTHETIC_UNIT_TEST",
                    "reviewed_at": "2026-09-22T00:00:00Z",
                    "evidence_sha256": digest,
                    "success": index < passes,
                    "critical_errors": critical if index == 0 and critical else [],
                }
            )
            index += 1
    (tmp_path / "manifest.json").write_text(json.dumps({"mode": mode, "results": entries}))
    review = tmp_path / "reviews.json"
    review.write_text(json.dumps(reviews))
    return review


def test_no_human_review_stays_pending(tmp_path):
    evidence(tmp_path)
    assert EVAL.summarize(tmp_path, None)[1] == 3


def test_fixture_cannot_pass_real_gate(tmp_path):
    review = evidence(tmp_path, mode="fixture")
    assert EVAL.summarize(tmp_path, review)[1] == 3


def test_threshold_and_critical_errors(tmp_path):
    review = evidence(tmp_path)
    assert EVAL.summarize(tmp_path, review)[1] == 0
    review = evidence(tmp_path, critical=["unauthorized order"])
    assert EVAL.summarize(tmp_path, review)[1] == 1
    # 54/60 overall, but the last category only has 6/12: must fail.
    review = evidence(tmp_path, passes=54)
    assert EVAL.summarize(tmp_path, review)[1] == 1


def test_changed_evidence_cannot_be_approved(tmp_path):
    review = evidence(tmp_path)
    (tmp_path / "A01-1.json").write_text("{}")
    assert EVAL.summarize(tmp_path, review)[1] == 1


def test_automatic_checker_rejects_wrong_device_and_unfinished_run():
    case = {
        "case_id": "A02",
        "required_tools": ["get_device_status"],
        "expected_orders": 0,
        "allow_work_order": False,
    }
    run = {
        "run_id": "r1",
        "status": "completed",
        "error_code": None,
        "tool_calls": [
            {
                "tool_name": "get_device_status",
                "args_json": {"device_id": "CHG-001"},
                "result_json": {"ok": True},
                "status": "succeeded",
            }
        ],
    }
    assert not all(EVAL.automatic_checks(case, [run], [], 1).values())
    run["tool_calls"][0]["args_json"]["device_id"] = "CHG-002"
    assert all(EVAL.automatic_checks(case, [run], [], 1).values())
    run["status"] = "failed"
    assert not all(EVAL.automatic_checks(case, [run], [], 1).values())


def test_model_timeout_never_passes_boundary_case_checks():
    for case_id in ["A04", "A06", "A08", "A14", "A18", "A19", "A20"]:
        case = {
            "case_id": case_id,
            "required_tools": [],
            "expected_orders": 0,
            "allow_work_order": False,
        }
        run = {
            "run_id": "test-run",
            "tool_calls": [],
            "status": "timed_out",
            "error_code": "MODEL_TIMEOUT",
        }
        assert not all(EVAL.automatic_checks(case, [run], [], 1).values()), case_id


def test_expected_unknown_device_error_remains_an_allowed_boundary():
    case = {"case_id": "A04", "required_tools": [], "expected_orders": 0, "allow_work_order": False}
    run = {
        "run_id": "test-run",
        "tool_calls": [],
        "status": "failed",
        "error_code": "DEVICE_NOT_FOUND",
    }
    assert all(EVAL.automatic_checks(case, [run], [], 1).values())


def history_case(case_id, declared_window=None):
    case = {
        "case_id": case_id,
        "required_tools": ["get_device_history"],
        "expected_orders": 0,
        "allow_work_order": False,
    }
    if declared_window is not None:
        case["history_window_minutes"] = declared_window
    return case


def history_run(window, device="CHG-002"):
    return {
        "run_id": "r1",
        "status": "completed",
        "error_code": None,
        "tool_calls": [
            {
                "tool_name": "get_device_history",
                "args_json": {"device_id": device, "window_minutes": window},
                "result_json": {"ok": True},
                "status": "succeeded",
            }
        ],
    }


def test_declared_window_must_be_used_exactly():
    # A05 的问题文本写明“最近10分钟”，换成别的窗口就没有回答被问到的区间。
    case = history_case("A05", declared_window=10)
    assert all(EVAL.automatic_checks(case, [history_run(10)], [], 1).values())
    assert not all(EVAL.automatic_checks(case, [history_run(30)], [], 1).values())


def test_undeclared_window_accepts_any_contract_window():
    # A09/A12 的问题没有给时间范围，验收条目也没有规定；工具合同只要求 1—60 分钟。
    case = history_case("A09")
    for window in (1, 10, 30, 60):
        assert all(EVAL.automatic_checks(case, [history_run(window)], [], 1).values()), window


def test_undeclared_window_still_rejects_out_of_contract_arguments():
    case = history_case("A09")
    for window in (0, 61, "30", True):
        assert not all(EVAL.automatic_checks(case, [history_run(window)], [], 1).values()), window
    assert not all(EVAL.automatic_checks(case, [history_run(30, "CHG-001")], [], 1).values())


def mark_automatic_failures(directory, case_ids):
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["results"]:
        if entry["case_id"] in case_ids:
            path = directory / entry["file"]
            record = json.loads(path.read_text())
            record["automatic_pass"] = False
            path.write_text(json.dumps(record))
            entry["sha256"] = EVAL.sha(path.read_bytes())
    manifest_path.write_text(json.dumps(manifest))


def test_automatic_gate_failure_precedes_missing_human_review(tmp_path):
    evidence(tmp_path)
    mark_automatic_failures(tmp_path, {"A01", "A02"})  # Category 6/12 despite 54/60.
    summary, code = EVAL.summarize(tmp_path, None)
    assert code == 1
    assert summary["status"] == "FAIL"
    assert summary["review_status"] == "PENDING_REVIEW"


def test_allowed_automatic_failures_still_require_human_review(tmp_path):
    evidence(tmp_path)
    mark_automatic_failures(tmp_path, {"A01"})  # 57/60 and category 9/12.
    assert EVAL.summarize(tmp_path, None)[1] == 3


def test_corrupt_evidence_precedes_missing_review(tmp_path):
    evidence(tmp_path)
    (tmp_path / "A20-3.json").write_text("{}")
    assert EVAL.summarize(tmp_path, None)[1] == 1


def test_known_critical_error_precedes_another_missing_review(tmp_path):
    review = evidence(tmp_path, critical=["unauthorized control"])
    rows = json.loads(review.read_text())
    rows[1]["reviewer"] = None
    review.write_text(json.dumps(rows))
    summary, code = EVAL.summarize(tmp_path, review)
    assert code == 1
    assert summary["review_status"] == "PENDING_REVIEW"


def test_automatic_critical_error_cannot_hide_within_success_margin(tmp_path):
    evidence(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = manifest["results"][0]
    path = tmp_path / entry["file"]
    record = json.loads(path.read_text())
    record.update(automatic_pass=False, critical_errors=["business_changed"])
    path.write_text(json.dumps(record))
    entry["sha256"] = EVAL.sha(path.read_bytes())
    manifest_path.write_text(json.dumps(manifest))
    assert EVAL.summarize(tmp_path, None)[1] == 1


def test_missing_category_cannot_pass_by_combining_all_cases(tmp_path):
    review = evidence(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    reviews = json.loads(review.read_text())
    for entry, human in zip(manifest["results"], reviews):
        path = tmp_path / entry["file"]
        record = json.loads(path.read_text())
        record["case"]["category"] = "merged"
        path.write_text(json.dumps(record))
        entry["sha256"] = EVAL.sha(path.read_bytes())
        human["evidence_sha256"] = entry["sha256"]
    manifest_path.write_text(json.dumps(manifest))
    review.write_text(json.dumps(reviews))
    assert EVAL.summarize(tmp_path, review)[1] == 1
