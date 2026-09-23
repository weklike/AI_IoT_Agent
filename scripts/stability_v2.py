"""Owned operations load: real MQTT/SQLite/browser, twelve read-only fixture patrols."""

import argparse
import json
import os
import re
import signal
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

from scripts.acceptance import environment, percentile
from tests.support.resources import ROOT, stack


class Exercise:
    def __init__(self, client, output):
        self.client, self.output = client, output
        self.operations = []

    def request(self, method, path, body=None, *, params=None):
        response = self.client.request(method, path, json=body, params=params)
        response.raise_for_status()
        return response.json()["data"]

    def save(self):
        (self.output / "operations.json").write_text(
            json.dumps(self.operations, ensure_ascii=False, indent=2)
        )

    def wait(self, path, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.request("GET", path)
            if predicate(result):
                return result
            time.sleep(0.2)
        raise RuntimeError("Operation did not reach its bounded terminal state: " + path)

    def start(self, device):
        result = self.request(
            "POST",
            f"/api/devices/{device}/charging/start",
            {"request_id": str(uuid4()), "requested_power_w": 20000},
        )
        record = {"kind": "start", "device_id": device, "accepted": result}
        self.operations.append(record)
        self.save()
        final = self.wait(
            "/api/device-commands/" + result["command_id"],
            lambda r: (
                r["verification_status"] in {"verified", "unconfirmed"}
                or r["status"] in {"rejected", "timed_out", "interrupted"}
            ),
            10,
        )
        record["final"] = final
        self.save()
        if final["verification_status"] != "verified":
            raise RuntimeError("Initial session was not verified")

    def plan(self, budget, strategy, minute):
        payload = {"request_id": str(uuid4()), "budget_w": budget, "strategy": strategy}
        if strategy == "priority":
            payload["device_priority"] = ["CHG-002", "CHG-001", "CHG-003"]
        preview = self.request("POST", "/api/power-plans", payload)
        identifier = preview["plan_id"]
        record = {"kind": "plan", "minute": minute, "preview": preview}
        self.operations.append(record)
        self.save()
        record["accepted"] = self.request(
            "POST", f"/api/power-plans/{identifier}/execute", {"request_id": str(uuid4())}
        )
        self.save()
        final = self.wait(
            "/api/power-plans/" + identifier,
            lambda r: r["status"] not in {"PREVIEW", "EXECUTING"},
            36,
        )
        record["final"] = final
        self.save()
        return final

    def patrol(self, minute):
        accepted = self.request(
            "POST", "/api/patrols", {"request_id": str(uuid4()), "window_minutes": 30}
        )
        record = {"kind": "patrol", "minute": minute, "accepted": accepted}
        self.operations.append(record)
        self.save()
        final = self.wait(
            "/api/patrols/" + accepted["report_id"],
            lambda r: r["status"] not in {"queued", "running"},
            96,
        )
        record["final"] = final
        record["run"] = self.request("GET", "/api/agent/runs/" + accepted["run_id"])
        self.save()


def resource_sample(project, client, minute):
    containers = [
        f"{project}-{service}-1" for service in ("backend", "simulator", "mqtt", "frontend")
    ]
    stats = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *containers],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    inspected = json.loads(
        subprocess.run(
            ["docker", "inspect", *containers],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout
    )
    volumes = {}
    for role in ("backend", "simulator"):
        completed = subprocess.run(
            [
                "docker",
                "exec",
                f"{project}-{role}-1",
                "/app/.venv/bin/python",
                "-m",
                "tests.support.resource_probe",
                "--role",
                role,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        volumes[role] = json.loads(completed.stdout)
    response = client.get("/api/test/runtime")
    response.raise_for_status()
    return {
        "minute": minute,
        "at": datetime.now(UTC).isoformat(),
        "host_loadavg": os.getloadavg(),
        "containers": [json.loads(line) for line in stats.stdout.splitlines()],
        "volumes": volumes,
        "states": [
            {
                "name": row["Name"],
                "status": row["State"]["Status"],
                "restart_count": row["RestartCount"],
            }
            for row in inspected
        ],
        "runtime": response.json(),
    }


def summarize_window(
    output, started, ended, history, logs, resources, operations, minutes, commit_logs=None
):
    acked = set(re.findall(r"telemetry_puback device_id=\S+ message_id=([0-9a-f-]+)", logs))
    stored = {row["message_id"]: row for row in history}
    committed = dict(
        re.findall(
            r"telemetry_committed message_id=([0-9a-f-]+) device_id=\S+ committed_at=(\S+)",
            commit_logs if commit_logs is not None else logs,
        )
    )
    latencies = [
        (
            datetime.fromisoformat(ts) - datetime.fromisoformat(stored[key]["sample_ts"])
        ).total_seconds()
        * 1000
        for key, ts in committed.items()
        if key in acked and key in stored
    ]
    ratio = len(acked & stored.keys()) / len(acked) if acked else 0
    plans = [op for op in operations if op["kind"] == "plan"]
    patrols = [op for op in operations if op["kind"] == "patrol"]
    browser = json.loads((output / "browser-observed.json").read_text())
    checks = {
        "reception_ratio": ratio >= 0.99,
        "unique_telemetry_measurements": len(latencies) >= 1000
        if minutes == 60
        else len(latencies) > 0,
        "telemetry_p95": bool(latencies) and 0 <= min(latencies) and percentile(latencies) <= 1000,
        "normal_temperature": all(row["temperature_c"] < 60 for row in history),
        "no_browser_errors": not browser["errors"],
        "browser_observed_live_samples": len(set(browser["observations"]) & acked) >= 20,
        "commit_logs_complete": len(latencies) == len(acked & stored.keys()),
        "all_plans_verified": len(plans) == 1 + sum(m <= minutes for m in (10, 20, 30, 40, 50))
        and all(op.get("final", {}).get("status") == "VERIFIED" for op in plans),
        "patrol_count_and_success": len(patrols) == (minutes + 4) // 5
        and all(op.get("final", {}).get("status") == "completed" for op in patrols),
        "resource_samples": len(resources) == minutes,
        "guardians_do_not_accumulate": all(
            row["runtime"]["guardians"] == {"mqtt-consumer": 1, "alarm-timer": 1, "patrol-timer": 1}
            for row in resources
        ),
        "managed_tasks_settled": all(
            row["runtime"]["managed"]
            == {"charging": 0, "power": 0, "scenario": 0, "scripts": 0, "agent": 0}
            for row in resources
        ),
        "no_container_restart": all(
            c["status"] == "running" and c["restart_count"] == 0
            for row in resources
            for c in row["states"]
        ),
        "no_unhandled_failures": not re.search(
            r"Traceback \(most recent call last\)|Task exception was never retrieved|database is locked|MQTT_QUEUE_FULL",
            logs,
        ),
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "kind": "acceptance" if minutes == 60 else "diagnostic",
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
        "window_seconds": minutes * 60,
        "drain_seconds": 10,
        "puback_unique": len(acked),
        "puback_total": len(re.findall(r"telemetry_puback device_id=", logs)),
        "matched_unique": len(acked & stored.keys()),
        "reception_ratio": ratio,
        "telemetry_count": len(latencies),
        "telemetry_p95_ms": percentile(latencies),
        "latencies_ms": latencies,
        "checks": checks,
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def run(output, minutes):
    output.mkdir(parents=True, exist_ok=False)
    env = environment()
    env["overrides"] = {"stability_window_seconds": minutes * 60}
    (output / "environment.json").write_text(json.dumps(env, indent=2))
    resources = []
    with stack(output, operations=True, monitor=True) as ports:
        base = "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"]
        with (
            httpx.Client(base_url=base, timeout=10) as client,
            (output / "browser.log").open("w") as browser_log,
        ):
            exercise = Exercise(client, output)
            deadline = time.monotonic() + 15
            while True:
                states = exercise.request("GET", "/api/devices")
                if len(states) == 3 and all(
                    r["data_fresh"] and r["schema_version"] == 2 for r in states
                ):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("Initial telemetry unavailable")
                time.sleep(0.2)
            for device in ("CHG-001", "CHG-002", "CHG-003"):
                exercise.start(device)
            if exercise.plan(60000, "equal", -1)["status"] != "VERIFIED":
                raise RuntimeError("Initial power plan not verified")
            browser = subprocess.Popen(
                ["node", str(ROOT / "frontend/scripts/hold.mjs")],
                env={**os.environ, "PERF_BASE_URL": base, "PERF_OUTPUT": str(output)},
                stdout=browser_log,
                stderr=subprocess.STDOUT,
            )
            try:
                limit = time.monotonic() + 20
                while not (output / "browser-ready").exists():
                    if browser.poll() is not None or time.monotonic() > limit:
                        raise RuntimeError("Browser failed to become ready")
                    time.sleep(0.1)
                started, tick = datetime.now(UTC), time.monotonic()
                ended = started + timedelta(minutes=minutes)
                (output / "window.json").write_text(
                    json.dumps(
                        {
                            "started_at": started.isoformat(),
                            "ended_at": ended.isoformat(),
                            "minutes": minutes,
                            "patrol_minutes": list(range(0, minutes, 5)),
                        },
                        indent=2,
                    )
                )
                print(
                    f"Operations window started {started.isoformat()}; {minutes} minutes",
                    flush=True,
                )
                exercise.patrol(0)
                for minute in range(1, minutes + 1):
                    target = tick + minute * 60
                    while time.monotonic() < target:
                        time.sleep(min(1, target - time.monotonic()))
                    if minute in (10, 20, 30, 40, 50):
                        index = minute // 10
                        exercise.plan(
                            45000 if index % 2 else 60000,
                            "equal" if index % 2 else "priority",
                            minute,
                        )
                    if minute % 5 == 0 and minute < minutes:
                        exercise.patrol(minute)
                    resources.append(resource_sample(ports["PROJECT"], client, minute))
                    (output / "resources.json").write_text(json.dumps(resources, indent=2))
                    print(f"Operations steady-state elapsed {minute}/{minutes} minutes", flush=True)
                time.sleep(10)
                history = []
                for device in ("CHG-001", "CHG-002", "CHG-003"):
                    history.extend(
                        exercise.request(
                            "GET",
                            f"/api/devices/{device}/telemetry",
                            params={
                                "from": (started - timedelta(seconds=5)).isoformat(),
                                "to": (ended + timedelta(seconds=10)).isoformat(),
                            },
                        )
                    )
                (output / "history.json").write_text(json.dumps(history, indent=2))
                command = [
                    "docker",
                    "compose",
                    "-p",
                    ports["PROJECT"],
                    "-f",
                    str(ROOT / "deploy/compose.yaml"),
                ]
                logs = subprocess.run(
                    command
                    + [
                        "logs",
                        "--no-color",
                        "--timestamps",
                        "--since",
                        started.isoformat(),
                        "--until",
                        ended.isoformat(),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                (output / "steady-window.log").write_text(logs)
                commit_logs = subprocess.run(
                    command
                    + [
                        "logs",
                        "--no-color",
                        "--timestamps",
                        "--since",
                        (started - timedelta(seconds=5)).isoformat(),
                        "--until",
                        (ended + timedelta(seconds=10)).isoformat(),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                ).stdout
                (output / "commit-window.log").write_text(commit_logs)
            finally:
                if browser.poll() is None:
                    browser.send_signal(signal.SIGTERM)
                if browser.wait(timeout=20):
                    raise RuntimeError("Browser recording failed")
            return summarize_window(
                output,
                started,
                ended,
                history,
                logs,
                resources,
                exercise.operations,
                minutes,
                commit_logs,
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--minutes",
        type=int,
        choices=range(1, 61),
        default=60,
        help="Short windows are diagnostics, never XAC-56",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        print("Evidence directory exists; choose a new output path.")
        return 2
    try:
        report = run(output, args.minutes)
        return 0 if report["status"] == "PASS" else 1
    except (OSError, subprocess.SubprocessError, RuntimeError, httpx.HTTPError) as error:
        output.mkdir(parents=True, exist_ok=True)
        (output / "failure.json").write_text(
            json.dumps(
                {"status": "FAIL", "error_type": type(error).__name__, "message": str(error)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
