import argparse
import os
import subprocess
from datetime import UTC, datetime

from tests.support.resources import ROOT, stack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--operations", action="store_true")
    parser.add_argument("--grep")
    parser.add_argument("--repeat-each", type=int, choices=range(1, 11), default=1)
    args = parser.parse_args()
    output = ROOT / "artifacts/acceptance/e2e" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output.mkdir(parents=True, exist_ok=False)
    outcomes = []
    suites = [
        ("normal", {}, ["--grep-invert", "@empty|@failure|@v2"]),
        ("empty", {"simulator": False}, ["--grep", "@empty"]),
        ("failures", {"failures": True}, ["--grep", "@failure"]),
        ("operations", {"operations": True}, ["--grep", "@v2"]),
    ]
    if args.operations:
        suites = [("operations", {"operations": True}, ["--grep", args.grep or "@v2"])]
    elif args.grep:
        suites = [("targeted", {}, ["--grep", args.grep])]
    for name, options, arguments in suites:
        destination = output / name
        with stack(destination, **options) as ports:
            env = {
                **os.environ,
                "E2E_BASE_URL": "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"],
                "E2E_OUTPUT": str(destination),
                "E2E_COMPOSE_PROJECT": ports["PROJECT"],
            }
            result = subprocess.run(
                [
                    "npm",
                    "exec",
                    "--",
                    "playwright",
                    "test",
                    *arguments,
                    "--repeat-each",
                    str(args.repeat_each),
                ],
                cwd=ROOT / "frontend",
                env=env,
            )
            outcomes.append(result.returncode)
    return max(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
