"""Repeat AC-33 query measurements with an isolated, full-hour dataset."""

import argparse
import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path

from scripts.acceptance import api_load, environment
from tests.support.resources import stack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "environment.json").write_text(json.dumps(environment(), indent=2))
    with stack(args.output, simulator=False) as ports:
        seeded = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                "APP_ENV=test",
                f"{ports['PROJECT']}-backend-1",
                "/app/.venv/bin/python",
                "-m",
                "tests.support.query_dataset",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        dataset = json.loads(seeded.stdout)
        (args.output / "dataset.json").write_text(json.dumps(dataset, indent=2))
        report = asyncio.run(
            api_load(
                "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"],
                datetime.fromisoformat(dataset["anchor"]),
                args.output,
            )
        )
        print(json.dumps({k: v for k, v in report.items() if k != "duration_ms"}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    try:
        code = main()
    except (OSError, subprocess.SubprocessError, RuntimeError):
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "detail": "Query environment unavailable; see build logs. Use a new output directory.",
                }
            )
        )
        code = 2
    raise SystemExit(code)
