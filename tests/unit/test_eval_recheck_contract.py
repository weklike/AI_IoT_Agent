import hashlib
import json

from eval import recheck


def evidence(tmp_path, monkeypatch, count=60):
    folder = tmp_path / "evidence"
    folder.mkdir()
    source = tmp_path / "eval"
    source.mkdir()
    (source / "run.py").write_text("checker")
    (source / "cases.jsonl").write_text("cases")
    cases = {
        f"A{i:02}": {"case_id": f"A{i:02}", "category": str((i - 1) // 4)} for i in range(1, 21)
    }
    monkeypatch.setattr(recheck, "ROOT", tmp_path)
    monkeypatch.setattr(recheck, "CASES", source / "cases.jsonl")
    monkeypatch.setattr(recheck, "current_cases", lambda: cases)
    monkeypatch.setattr(recheck.ENTRY, "automatic_checks", lambda *args: {"checked": True})
    entries = []
    for n in range(count):
        identity, repeat = f"A{n // 3 + 1:02}", n % 3 + 1
        path = folder / f"{identity}-{repeat}.json"
        path.write_text(
            json.dumps(
                {
                    "case": cases[identity],
                    "repeat": repeat,
                    "runs": [{"run_id": str(n), "error_code": None}],
                    "orders": [],
                    "automatic_checks": {"checked": True},
                    "automatic_pass": True,
                }
            )
        )
        entries.append(
            {
                "case_id": identity,
                "repeat": repeat,
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "results": entries,
                "model": "test",
                "mode": "real",
                "environment": {"git_sha": "test"},
                "cases_sha256": "test",
            }
        )
    )
    return folder


def test_recheck_complete_automatic_results_still_require_human_review(tmp_path, monkeypatch):
    report, code = recheck.recheck(evidence(tmp_path, monkeypatch), "测试退出码合同")
    assert report["status"] == "PENDING_REVIEW"
    assert code == 3


def test_recheck_missing_cases_cannot_pass_even_when_numerical_threshold_is_met(
    tmp_path, monkeypatch
):
    report, code = recheck.recheck(evidence(tmp_path, monkeypatch, 57), "测试完整分母")
    assert report["status"] == "FAIL"
    assert code == 1
