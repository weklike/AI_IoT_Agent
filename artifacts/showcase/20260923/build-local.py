"""Offline showcase build from verified local dependency images.

Run from the repository root: uv run python artifacts/showcase/20260923/build-local.py

The frontend is type-checked and built here, so the image always carries the current dist.
Images are tagged showcase-* only: the test-{digest} tags belong to tests/support/resources.py,
which skips its own build when such a tag exists.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime

from tests.support.resources import ROOT, source_digest

BASE = {
    "backend": "charge-ops-backend:test-94f8cb9ab56df832",
    "frontend": "charge-ops-frontend:test-94f8cb9ab56df832",
}
# COPY never deletes, so remove what the base image already holds before copying current sources.
DOCKERFILES = {
    "backend": (
        "RUN rm -rf backend simulator knowledge tests/support\n"
        "COPY backend backend\nCOPY simulator simulator\nCOPY knowledge knowledge\n"
        "COPY tests/support tests/support\n"
        "RUN uv sync --offline --locked --no-dev\n"
    ),
    "frontend": (
        "RUN rm -rf /usr/share/nginx/html/assets /usr/share/nginx/html/index.html\n"
        "COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf\n"
        "COPY frontend/dist/ /usr/share/nginx/html/\n"
    ),
}
DOCKERIGNORE = {
    "backend": "**\n!backend\n!simulator\n!knowledge\n!tests/support\n**/__pycache__\n",
    "frontend": "**\n!frontend/dist\n!frontend/dist/**\n!deploy/nginx.conf\n",
}


def run(record: dict, name: str, command: list[str], log) -> int:
    log.write(f"$ {' '.join(command)}\n")
    log.flush()
    code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
    record["steps"].append({"step": name, "exit": code})
    return code


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = ROOT / "artifacts/showcase/20260923" / f"build-{stamp}"
    out.mkdir(parents=True, exist_ok=False)
    record: dict = {"status": "FAIL", "started_at": datetime.now(UTC).isoformat(), "steps": []}
    with open(out / "build.log", "w", encoding="utf-8") as log:
        for name in ("typecheck", "build"):
            if run(record, "npm " + name, ["npm", "--prefix", "frontend", "run", name], log):
                break
        else:
            for filename in ("uv.lock", "pyproject.toml"):
                cached = subprocess.run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--entrypoint",
                        "cat",
                        BASE["backend"],
                        "/app/" + filename,
                    ],
                    capture_output=True,
                    check=True,
                ).stdout
                if cached != (ROOT / filename).read_bytes():
                    record["steps"].append({"step": "dependency match " + filename, "exit": 1})
                    break
            else:
                record["uv_lock_and_pyproject"] = "exact byte match with " + BASE["backend"]
                # Digest after npm build: dist is not part of it, frontend/src is.
                digest = source_digest()
                record["source_digest"] = digest
                record["images"] = {}
                for role, body in DOCKERFILES.items():
                    dockerfile = out / f"{role}.Dockerfile"
                    dockerfile.write_text("FROM " + BASE[role] + "\n" + body)
                    (out / f"{role}.Dockerfile.dockerignore").write_text(DOCKERIGNORE[role])
                    tags = [
                        f"charge-ops-{role}:showcase-20260923",
                        f"charge-ops-{role}:showcase-{digest}",
                    ]
                    command = ["docker", "build", "--network=none", "-f", str(dockerfile)]
                    command += [arg for tag in tags for arg in ("-t", tag)] + ["."]
                    if run(record, "docker build " + role, command, log):
                        break
                    record["images"][role] = tags
                else:
                    record["status"] = "PASS"
    record["finished_at"] = datetime.now(UTC).isoformat()
    (out / "local-build.json").write_text(json.dumps(record, indent=2) + "\n")
    print(out / "local-build.json", record["status"])
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
