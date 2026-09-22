"""Owned Compose resources; never reuse or clear a developer instance."""

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
def stack():
    project = f"charge-smoke-{uuid4().hex[:12]}"
    env = os.environ.copy()
    ports = dict(
        MQTT_PUBLISH_PORT=str(free_port()),
        BACKEND_PUBLISH_PORT=str(free_port()),
        FRONTEND_PUBLISH_PORT=str(free_port()),
    )
    env.update(ports)
    env.update(
        LLM_MODE="fixture",
        LLM_BASE_URL="",
        LLM_MODEL="",
        LLM_API_KEY="",
        MQTT_TOPIC_PREFIX=f"charge-test/{project}/v1",
    )
    command = ["docker", "compose", "-p", project, "-f", str(ROOT / "deploy/compose.yaml")]
    try:
        subprocess.run(
            command + ["up", "-d", "--build", "--wait", "--wait-timeout", "120"],
            check=True,
            env=env,
            timeout=600,
        )
        yield ports
    finally:
        subprocess.run(
            command + ["down", "-v", "--remove-orphans"], check=True, env=env, timeout=60
        )
