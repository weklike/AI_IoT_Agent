import os
import subprocess
from datetime import UTC, datetime

from tests.support.resources import ROOT, stack


def main():
    output = ROOT / "artifacts/acceptance/e2e" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output.mkdir(parents=True, exist_ok=False)
    outcomes = []
    for name, options, arguments in [
        ("normal", {}, ["--grep-invert", "@empty|@failure"]),
        ("empty", {"simulator": False}, ["--grep", "@empty"]),
        ("failures", {"failures": True}, ["--grep", "@failure"]),
    ]:
        destination = output / name
        with stack(destination, **options) as ports:
            env = {
                **os.environ,
                "E2E_BASE_URL": "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"],
                "E2E_OUTPUT": str(destination),
            }
            result = subprocess.run(
                ["npm", "exec", "--", "playwright", "test", *arguments],
                cwd=ROOT / "frontend",
                env=env,
            )
            outcomes.append(result.returncode)
    return max(outcomes)


if __name__ == "__main__":
    raise SystemExit(main())
