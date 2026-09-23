"""Execute v2 automatic subassertions without promoting them to complete XAC/M gates."""

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.acceptance import environment
from scripts.acceptance_v2_contract import ASSERTIONS, GROUPS, SUITES
from scripts.evidence import source_hashes
from tests.support.resources import ROOT


def status_code(statuses):
    if "BLOCKED" in statuses:
        return 2
    if any(s in {"FAIL", "NOT_RUN"} for s in statuses):
        return 1
    if "PENDING_REVIEW" in statuses:
        return 3
    return 0


def junit_assertions(path, identifiers):
    cases = list(ET.parse(path).iter("testcase")) if path.exists() else []
    result = {}
    for number in identifiers:
        label, names = ASSERTIONS[number]
        evidence = []
        missing = []
        for name in names:
            matched = [
                c
                for c in cases
                if c.attrib["name"] == name or c.attrib["name"].startswith(name + "[")
            ]
            if not matched:
                missing.append(name)
            for case in matched:
                status = (
                    "FAIL"
                    if any(c.tag in {"failure", "error"} for c in case)
                    else "NOT_RUN"
                    if any(c.tag == "skipped" for c in case)
                    else "PASS"
                )
                evidence.append(
                    {
                        "test": case.attrib["name"],
                        "class": case.attrib.get("classname"),
                        "status": status,
                        "seconds": float(case.attrib.get("time", 0)),
                    }
                )
        statuses = [e["status"] for e in evidence] + (["NOT_RUN"] if missing else [])
        automatic = (
            "FAIL"
            if "FAIL" in statuses
            else "NOT_RUN"
            if not statuses or "NOT_RUN" in statuses
            else "PASS"
        )
        result[f"XAC-{number:02}"] = {
            "status": "NOT_RUN",
            "scope": "完整XAC仍需逐项核对其余子断言，不能由测试名称推定",
            "automatic_subassertions": {
                "status": automatic,
                "scope": label,
                "missing_tests": missing,
                "evidence_file": str(path),
                "tests": evidence,
            },
        }
    return result


def execute(command, output, name):
    log = output / (name + ".log")
    try:
        with log.open("w") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        code = result.returncode
        status = {0: "PASS", 1: "FAIL", 2: "BLOCKED", 3: "PENDING_REVIEW"}.get(code, "FAIL")
    except OSError as error:
        log.write_text(type(error).__name__ + "\n")
        code, status = 2, "BLOCKED"
    return {"status": status, "exit_code": code, "command": command, "log": str(log)}


def verify_runtime_compatibility(directory, compatibility_file=None):
    env = json.loads((directory / "environment.json").read_text())
    paths = [
        "backend",
        "simulator",
        "knowledge",
        "frontend/src",
        "deploy",
        "uv.lock",
        "frontend/package-lock.json",
        "tests/support/monitor_app.py",
        "tests/support/resource_probe.py",
        "frontend/scripts/hold.mjs",
    ]
    # Compare both committed and pending changes to the exact source used for the run.
    diff = subprocess.run(
        ["git", "diff", "--name-only", env["git_sha"], "--", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    current = environment()
    if env["locks"] != current["locks"]:
        return False
    if not diff.stdout:
        return True
    if compatibility_file is None:
        return False
    note = json.loads(compatibility_file.read_text())
    changed = set(diff.stdout.splitlines())
    allowed = {
        "backend/app/agent/prompts.py",
        "backend/app/agent/read_queries.py",
        "backend/app/power/service.py",
    }
    if (
        note.get("kind") != "fixture-stability-source-comparison"
        or note.get("source_commit") != env["git_sha"]
    ):
        return False
    if changed != set(note.get("files", {})) or not changed <= allowed:
        return False
    patrols = [
        op
        for op in json.loads((directory / "operations.json").read_text())
        if op["kind"] == "patrol"
    ]
    if not patrols or any(op.get("run", {}).get("llm_mode") != "fixture" for op in patrols):
        return False
    for path in changed:
        before = subprocess.check_output(["git", "show", env["git_sha"] + ":" + path], cwd=ROOT)
        proof = note["files"][path]
        if (
            hashlib.sha256(before).hexdigest() != proof["before_sha256"]
            or hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != proof["after_sha256"]
        ):
            return False
        if not proof.get("unchanged_behavior_reason"):
            return False
    return True


def reuse_stability(directory, output, compatibility_file=None):
    import shutil
    from datetime import datetime

    from scripts.stability_v2 import summarize_window

    if not verify_runtime_compatibility(directory, compatibility_file):
        return {"status": "NOT_RUN", "message": "运行代码/依赖不同，拒绝沿用稳定性证据"}
    original = json.loads((directory / "report.json").read_text())
    if original.get("kind") != "acceptance" or original.get("window_seconds") != 3600:
        return {"status": "NOT_RUN", "message": "必须是完整60分钟operations报告，短时诊断不能沿用"}
    if compatibility_file:
        shutil.copyfile(compatibility_file, output / "stability-source-comparison.json")
    destination = output / "stability-revalidated"
    destination.mkdir()
    shutil.copyfile(directory / "browser-observed.json", destination / "browser-observed.json")
    report = summarize_window(
        destination,
        datetime.fromisoformat(original["started_at"]),
        datetime.fromisoformat(original["ended_at"]),
        json.loads((directory / "history.json").read_text()),
        (directory / "steady-window.log").read_text(),
        json.loads((directory / "resources.json").read_text()),
        json.loads((directory / "operations.json").read_text()),
        60,
        (directory / "commit-window.log").read_text(),
    )
    return {
        "status": report["status"],
        "source": str(directory),
        "evidence": str(destination / "report.json"),
        "compatibility": "Exact source comparison; any allowed additive metadata/prompt changes are bound to before/after hashes in the attached note",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite", choices=["iot", "ai", "resilience", "performance"], required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--reuse-stability",
        type=Path,
        help="Validate existing full-hour evidence; never overwrite it",
    )
    parser.add_argument(
        "--compatibility-file",
        type=Path,
        help="Hash-bound explanation of additive metadata/fixture-ignored prompt changes only",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        print("Evidence directory exists; choose a new output path.")
        return 2
    output.mkdir(parents=True)
    env = environment()
    env["source_hashes"] = source_hashes()
    (output / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2))
    report = {
        "suite": args.suite,
        "scope": "自动子断言；不表示完整XAC、M1—M4或真人复核通过",
        "steps": {},
        "results": {},
    }
    if args.suite in SUITES:
        definition = SUITES[args.suite]
        paths = list(
            dict.fromkeys(path for group in definition["groups"] for path in GROUPS[group])
        )
        command = ["uv", "run", "pytest", *paths, "-q", f"--junitxml={output}/backend.xml"]
        step = execute(command, output, "pytest")
        # Pytest 2 is collection/interruption, not automatically an unavailable environment.
        if step["exit_code"] in {2, 3, 4, 5}:
            step["status"] = "FAIL"
        report["steps"]["pytest"] = step
        report["results"] = junit_assertions(output / "backend.xml", definition["ids"])
        for key, value in report["results"].items():
            report["steps"][key] = value["automatic_subassertions"]
        if args.suite == "ai":
            step = execute(
                [
                    "uv",
                    "run",
                    "python",
                    "eval/retrieval/run.py",
                    "--dataset",
                    "eval/retrieval/test.jsonl",
                    "--output",
                    str(output / "retrieval"),
                ],
                output,
                "retrieval",
            )
            report["steps"]["retrieval"] = step
            report["results"]["XAC-42"] = {
                "status": step["status"],
                "scope": "冻结32条检索完整验收；不是模型语义评测",
                "evidence": str(output / "retrieval/report.json"),
            }
    else:
        for name, script in [
            ("original_queries", "scripts/query_performance.py"),
            ("new_queries", "scripts/query_performance_v2.py"),
            ("visibility", "scripts/control_visibility_v2.py"),
            ("power_protection", "scripts/power_protection_v2.py"),
        ]:
            if not (ROOT / script).exists():
                report["steps"][name] = {
                    "status": "NOT_RUN",
                    "message": "所需验收入口尚未实现",
                    "script": script,
                }
                continue
            report["steps"][name] = execute(
                ["uv", "run", "python", script, "--output", str(output / name)], output, name
            )
        if args.reuse_stability:
            try:
                report["steps"]["stability"] = reuse_stability(
                    args.reuse_stability.resolve(), output, args.compatibility_file
                )
            except (OSError, KeyError, ValueError, subprocess.SubprocessError) as error:
                report["steps"]["stability"] = {
                    "status": "FAIL",
                    "error": type(error).__name__,
                    "message": "既有稳定性证据不完整或无效",
                }
        else:
            report["steps"]["stability"] = execute(
                [
                    "uv",
                    "run",
                    "python",
                    "scripts/stability_v2.py",
                    "--output",
                    str(output / "stability"),
                ],
                output,
                "stability",
            )
        report["results"] = {
            "XAC-55": {"status": "NOT_RUN", "scope": "分项详见steps，默认预算/反馈/查询均须完成"},
            "XAC-56": {
                "status": report["steps"]["stability"]["status"],
                "scope": "60分钟operations稳态",
            },
        }
    code = status_code([step["status"] for step in report["steps"].values()])
    report["status"] = {0: "PASS", 1: "FAIL", 2: "BLOCKED", 3: "PENDING_REVIEW"}[code]
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "status": report["status"],
                "scope": report["scope"],
                "evidence": str(output / "report.json"),
            },
            ensure_ascii=False,
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
