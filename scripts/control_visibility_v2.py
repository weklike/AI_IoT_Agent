"""Twenty actual controls and alarm samples, timed against visible browser state."""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from scripts.acceptance import environment, percentile
from tests.support.resources import ROOT, stack


def assess(directory, count):
    browser = json.loads((directory / "browser-results.json").read_text())
    logs = (directory / "compose.log").read_text()
    commits = dict(
        re.findall(
            r"telemetry_committed message_id=([0-9a-f-]+) device_id=\S+ committed_at=(\S+)", logs
        )
    )
    for alarm in browser["alarms"]:
        if alarm["status"] != "PENDING_COMMIT_LOG":
            continue
        key = alarm["created_event"]["detail"]["evidence"]["message_id"]
        committed = commits.get(key)
        if committed:
            alarm["committed_at"] = committed
            alarm["latency_ms"] = (
                datetime.fromisoformat(alarm["seen_at"]) - datetime.fromisoformat(committed)
            ).total_seconds() * 1000
            alarm["status"] = "PASS" if 0 <= alarm["latency_ms"] <= 4000 else "FAIL"
        else:
            alarm["status"] = "FAIL"
            alarm["error"] = "Trigger commit log missing"
    groups = {}
    for name in ("controls", "alarms"):
        rows = browser[name]
        groups[name] = {
            "requested": count,
            "executed": len(rows),
            "within_4s": sum(row["status"] == "PASS" for row in rows),
            "p95_ms": percentile([row["latency_ms"] for row in rows if "latency_ms" in row]),
            "records": rows,
        }
    required = 19 if count == 20 else count
    passed = not browser["errors"] and all(
        row["executed"] == count and row["within_4s"] >= required for row in groups.values()
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "kind": "acceptance" if count == 20 else "diagnostic",
        "scope": "ACK→fresh correct control UI; actual alarm transaction commit→UI",
        "groups": groups,
        "browser_errors": browser["errors"],
    }
    (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, choices=[2, 20], default=20)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        print("Evidence directory exists; choose another path")
        return 2
    output.mkdir(parents=True)
    (output / "environment.json").write_text(json.dumps(environment(), indent=2))
    try:
        with stack(output, operations=True) as ports:
            env = {
                **os.environ,
                "PERF_BASE_URL": "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"],
                "PERF_OUTPUT": str(output),
                "PERF_SAMPLES": str(args.samples),
            }
            with (output / "browser.log").open("w") as log:
                subprocess.run(
                    ["node", str(ROOT / "frontend/scripts/visibility.mjs")],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=900,
                )
        report = assess(output, args.samples)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "kind": report["kind"],
                    "groups": {
                        name: {k: v for k, v in value.items() if k != "records"}
                        for name, value in report["groups"].items()
                    },
                },
                indent=2,
            )
        )
        return 0 if report["status"] == "PASS" else 1
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        status = "FAIL" if (output / "browser-results.json").exists() else "BLOCKED"
        (output / "failure.json").write_text(
            json.dumps(
                {"status": status, "error_type": type(error).__name__, "message": str(error)},
                indent=2,
            )
        )
        return 1 if status == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
