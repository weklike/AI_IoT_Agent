"""Owned Compose resources; never reuse or clear a developer instance."""

import hashlib
import json
import os
import socket
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def broker():
    project = f"charge-test-{uuid4().hex[:12]}"
    port = free_port()
    prefix = f"charge-test/{project}/v1"
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        config = Path(directory) / "compose.json"
        config.write_text(
            json.dumps(
                {
                    "services": {
                        "mqtt": {
                            "image": "eclipse-mosquitto:2.0.22",
                            "ports": [f"127.0.0.1:{port}:1883"],
                            "volumes": [
                                f"{ROOT}/deploy/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro"
                            ],
                            "healthcheck": {
                                "test": [
                                    "CMD",
                                    "mosquitto_pub",
                                    "-h",
                                    "127.0.0.1",
                                    "-t",
                                    "health",
                                    "-m",
                                    "ready",
                                ],
                                "interval": "1s",
                                "timeout": "2s",
                                "retries": 20,
                            },
                        }
                    }
                }
            )
        )
        command = ["docker", "compose", "-p", project, "-f", str(config)]
        try:
            subprocess.run(
                command + ["up", "-d", "--wait", "--wait-timeout", "40"],
                check=True,
                capture_output=True,
                text=True,
                timeout=180,
            )
            yield port, prefix
        finally:
            subprocess.run(
                command + ["down", "-v", "--remove-orphans"],
                check=True,
                capture_output=True,
                text=True,
                timeout=40,
            )


@contextmanager
def stack(
    output: Path | None = None,
    *,
    simulator: bool = True,
    failures: bool = False,
    operations: bool = False,
    monitor: bool = False,
):
    project = f"charge-smoke-{uuid4().hex[:12]}"
    env = os.environ.copy()
    ports = dict(
        MQTT_PUBLISH_PORT=str(free_port()),
        BACKEND_PUBLISH_PORT=str(free_port()),
        FRONTEND_PUBLISH_PORT=str(free_port()),
    )
    env.update(ports)
    env.update(
        SIMULATOR_MODE="operations" if operations else "legacy",
        LLM_MODE="fixture",
        LLM_BASE_URL="",
        LLM_MODEL="",
        LLM_API_KEY="",
        MQTT_TOPIC_PREFIX=f"charge-test/{project}/v1",
    )
    sources = sorted(
        [
            p
            for directory in (
                "backend",
                "simulator",
                "knowledge",
                "tests/support",
                "deploy",
                "frontend/src",
            )
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        ]
        + [
            ROOT / p
            for p in (
                "pyproject.toml",
                "uv.lock",
                "frontend/package.json",
                "frontend/package-lock.json",
                "frontend/vite.config.ts",
                "frontend/tsconfig.json",
                "frontend/index.html",
            )
        ]
    )
    digest = hashlib.sha256(
        b"".join(str(p.relative_to(ROOT)).encode() + p.read_bytes() for p in sources)
    ).hexdigest()[:16]
    env.update(
        BACKEND_IMAGE=f"charge-ops-backend:test-{digest}",
        FRONTEND_IMAGE=f"charge-ops-frontend:test-{digest}",
    )
    command = ["docker", "compose", "-p", project, "-f", str(ROOT / "deploy/compose.yaml")]
    override = None
    if failures and monitor:
        raise ValueError("Failure and monitoring test apps cannot be combined")
    if failures or monitor:
        override = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(
            {
                "services": {
                    "backend": {
                        "environment": {"APP_ENV": "test"},
                        "command": [
                            "/app/.venv/bin/uvicorn",
                            (
                                "tests.support.failure_app:create_test_app"
                                if failures
                                else "tests.support.monitor_app:create_test_app"
                            ),
                            "--factory",
                            "--host",
                            "0.0.0.0",
                            "--port",
                            "8000",
                            "--workers",
                            "1",
                        ],
                    }
                }
            },
            override,
        )
        override.close()
        command += ["-f", override.name]
    try:
        import time

        available = all(
            subprocess.run(["docker", "image", "inspect", env[key]], capture_output=True).returncode
            == 0
            for key in ("BACKEND_IMAGE", "FRONTEND_IMAGE")
        )
        if not available:
            dependency_image = os.environ.get("CHARGE_TEST_DEPENDENCY_IMAGE")
            if dependency_image:
                # Explicit offline fallback: only reuse an image with exactly the same package contract.
                for filename in ("uv.lock", "pyproject.toml"):
                    copied = subprocess.run(
                        [
                            "docker",
                            "run",
                            "--rm",
                            "--entrypoint",
                            "cat",
                            dependency_image,
                            "/app/" + filename,
                        ],
                        check=True,
                        capture_output=True,
                        timeout=30,
                    )
                    if copied.stdout != (ROOT / filename).read_bytes():
                        raise RuntimeError("Cached dependency image does not match " + filename)
                with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile") as dockerfile:
                    dockerfile.write(
                        "FROM " + dependency_image + "\n"
                        "COPY backend backend\nCOPY simulator simulator\nCOPY knowledge knowledge\n"
                        "COPY tests/support tests/support\n"
                        "RUN uv sync --offline --locked --no-dev\n"
                    )
                    dockerfile.flush()
                    subprocess.run(
                        [
                            "docker",
                            "build",
                            "-f",
                            dockerfile.name,
                            "-t",
                            env["BACKEND_IMAGE"],
                            str(ROOT),
                        ],
                        check=True,
                        timeout=180,
                    )
                subprocess.run(command + ["build", "frontend"], check=True, env=env, timeout=600)
                if output:
                    output.mkdir(parents=True, exist_ok=True)
                    (output / "dependency-cache.json").write_text(
                        json.dumps(
                            {
                                "image": dependency_image,
                                "uv_lock_and_pyproject": "exact_match",
                                "install": "uv sync --offline --locked --no-dev",
                            },
                            indent=2,
                        )
                    )
            else:
                subprocess.run(command + ["build"], check=True, env=env, timeout=600)
        started = time.monotonic()
        subprocess.run(
            command
            + ["up", "-d", "--wait", "--wait-timeout", "120"]
            + ([] if simulator else ["mqtt", "backend", "frontend"]),
            check=True,
            env=env,
            timeout=150,
        )
        ports["PROJECT"] = project
        ports["STARTUP_SECONDS"] = str(time.monotonic() - started)
        yield ports
    finally:
        if output:
            output.mkdir(parents=True, exist_ok=True)
            log = subprocess.run(
                command + ["logs", "--no-color", "--timestamps"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            (output / "compose.log").write_text(log.stdout + log.stderr)
        subprocess.run(
            command + ["down", "-v", "--remove-orphans"], check=True, env=env, timeout=60
        )
        if override:
            Path(override.name).unlink(missing_ok=True)
