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
