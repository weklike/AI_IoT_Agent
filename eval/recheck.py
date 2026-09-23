"""按当前判定重算已保存的评测证据。原始案例文件与 manifest 不修改，只追加一份重算记录。"""

import argparse
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("evaluation_entry", Path(__file__).parent / "run.py")
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "eval/cases.jsonl"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_cases() -> dict[str, dict]:
    return {
        json.loads(line)["case_id"]: json.loads(line) for line in CASES.read_text().splitlines()
    }


def recheck(directory: Path, note: str) -> tuple[dict, int]:
    manifest = json.loads((directory / "manifest.json").read_text())
    cases = current_cases()
    results, categories = [], {}
    for entry in manifest["results"]:
        path = directory / entry["file"]
        stored = digest(path)
        if stored != entry["sha256"]:
            raise SystemExit(f"证据摘要不符，拒绝重算：{entry['file']}")
        record = json.loads(path.read_text())
        case = dict(cases[entry["case_id"]])
        # 只允许新增判定所需的声明字段；问题、工具、授权等必须与执行时逐字一致。
        for key, value in record["case"].items():
            if case.get(key) != value:
                raise SystemExit(f"案例定义与执行时不一致，拒绝重算：{entry['file']} 字段 {key}")
        runs = record["runs"]
        # 每个 run 在库中对应一行 AgentRun，执行时的 run_count 可由唯一 run_id 精确还原。
        run_count = len({run["run_id"] for run in runs})
        checks = ENTRY.automatic_checks(case, runs, record["orders"], run_count)
        passed = all(checks.values())
        changed = sorted(
            name for name, value in checks.items() if record["automatic_checks"].get(name) != value
        )
        group = categories.setdefault(
            record["case"]["category"], {"executed": 0, "original_pass": 0, "rechecked_pass": 0}
        )
        group["executed"] += 1
        group["original_pass"] += int(record["automatic_pass"])
        group["rechecked_pass"] += int(passed)
        results.append(
            {
                "case_id": entry["case_id"],
                "repeat": entry["repeat"],
                "file": entry["file"],
                "sha256": stored,
                "original_automatic_pass": record["automatic_pass"],
                "rechecked_automatic_pass": passed,
                "changed_checks": changed,
                "checks": checks,
                "errors": sorted({run["error_code"] for run in runs if run["error_code"]}),
                "human_review": "PENDING_REVIEW",
            }
        )
    original_pass = sum(r["original_automatic_pass"] for r in results)
    rechecked_pass = sum(r["rechecked_automatic_pass"] for r in results)
    complete = len(results) == 60 and {(r["case_id"], r["repeat"]) for r in results} == {
        (f"A{case:02}", repeat) for case in range(1, 21) for repeat in range(1, 4)
    }
    thresholds = (
        complete
        and len(categories) == 5
        and all(group["executed"] == 12 for group in categories.values())
        and rechecked_pass >= 54
        and all(group["rechecked_pass"] >= 9 for group in categories.values())
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "PENDING_REVIEW" if thresholds else "FAIL",
        "scope": "仅按当前判定重算已保存轨迹，未重新调用模型，未做人工语义复核。",
        "note": note,
        "evidence_dir": str(directory.resolve().relative_to(ROOT)),
        "model": manifest["model"],
        "source_commit": manifest["environment"]["git_sha"],
        "checker_sha256": digest(ROOT / "eval/run.py"),
        "cases_sha256_at_run": manifest["cases_sha256"],
        "cases_sha256_now": digest(CASES),
        "run_count_source": "由证据中的唯一 run_id 还原",
        "executed_cases": len(results),
        "complete_case_set": complete,
        "original_automatic_pass": original_pass,
        "rechecked_automatic_pass": rechecked_pass,
        "automatic_thresholds_met": thresholds,
        "human_review": "PENDING_REVIEW",
        "categories": categories,
        "changed_cases": [r for r in results if r["changed_checks"]],
        "results": results,
    }
    return report, (3 if thresholds else 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True, help="已保存的评测证据目录")
    parser.add_argument("--note", required=True, help="重算原因，写入记录")
    parser.add_argument("--output", type=Path, help="默认写入证据目录的 automatic-recheck.json")
    args = parser.parse_args()
    output = args.output or args.dir / "automatic-recheck.json"
    if output.exists():
        print("重算记录已存在，请使用新文件名，不能覆盖旧记录。")
        return 2
    report, code = recheck(args.dir, args.note)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "original_automatic_pass",
                    "rechecked_automatic_pass",
                    "automatic_thresholds_met",
                    "categories",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
