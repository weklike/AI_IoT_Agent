"""Execute isolated acceptance suites. Never infer PASS for assertions not measured."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import re
import signal
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from tests.support.resources import ROOT, stack


def percentile(values, q=0.95):
    return sorted(values)[math.ceil(q * len(values)) - 1] if values else None


def environment():
    def output(args):
        return subprocess.run(args, capture_output=True, text=True).stdout.strip()

    return {
        "executed_at": datetime.now(UTC).isoformat(),
        "git_sha": output(["git", "rev-parse", "HEAD"]),
        "working_tree": output(["git", "status", "--short"]),
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        ),
        "meminfo": Path("/proc/meminfo").read_text().splitlines()[:3],
        "node": output(["node", "--version"]),
        "compose": output(["docker", "compose", "version"]),
        "locks": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in ("uv.lock", "frontend/package-lock.json")
        },
    }


async def api_load(base, started, output):
    durations, errors = [], []
    params = {"from": (started - timedelta(minutes=10)).isoformat(), "to": started.isoformat()}
    async with httpx.AsyncClient(base_url=base, timeout=10) as client:
        for _ in range(50):
            await client.get("/api/devices/CHG-002")

        async def worker(offset):
            for i in range(100):
                before = time.monotonic()
                path = (
                    "/api/devices/CHG-002" if (i + offset) % 2 else "/api/devices/CHG-002/telemetry"
                )
                try:
                    response = await client.get(
                        path, params=params if path.endswith("telemetry") else None
                    )
                    elapsed = (time.monotonic() - before) * 1000
                    durations.append(elapsed)
                    if response.status_code != 200:
                        errors.append({"status": response.status_code, "duration_ms": elapsed})
                except httpx.HTTPError as exc:
                    errors.append(
                        {
                            "error": type(exc).__name__,
                            "duration_ms": (time.monotonic() - before) * 1000,
                        }
                    )

        await asyncio.gather(*(worker(i) for i in range(10)))
    report = {
        "warmup": 50,
        "concurrency": 10,
        "requests": 1000,
        "duration_ms": durations,
        "errors": errors,
        "p95_ms": percentile(durations),
        "status": "PASS" if not errors and percentile(durations) <= 500 else "FAIL",
    }
    (output / "api-load.json").write_text(json.dumps(report, indent=2))
    return report


def stability(output):
    output.mkdir(parents=True, exist_ok=False)
    (output / "environment.json").write_text(json.dumps(environment(), indent=2))
    with stack(output) as ports:
        base = "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"]
        with (output / "browser.log").open("w") as log:
            browser = subprocess.Popen(
                ["node", str(ROOT / "frontend/scripts/hold.mjs")],
                env={**os.environ, "PERF_BASE_URL": base, "PERF_OUTPUT": str(output)},
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                ready_limit = time.monotonic() + 20
                while not (output / "browser-ready").exists():
                    if browser.poll() is not None or time.monotonic() > ready_limit:
                        raise RuntimeError("Browser did not become ready; see browser.log")
                    time.sleep(0.1)
                started, tick = datetime.now(UTC), time.monotonic()
                resource_samples = []
                print("60-minute steady-state window started " + started.isoformat(), flush=True)
                for minute in range(60):
                    target = tick + (minute + 1) * 60
                    while time.monotonic() < target:
                        time.sleep(min(1, target - time.monotonic()))
                    stats = subprocess.run(
                        [
                            "docker",
                            "stats",
                            "--no-stream",
                            "--format",
                            "{{json .}}",
                            *[
                                f"{ports['PROJECT']}-{service}-1"
                                for service in ("backend", "simulator", "mqtt", "frontend")
                            ],
                        ],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    resource_samples.append(
                        {"minute": minute + 1, "loadavg": os.getloadavg(), "stats": stats.stdout}
                    )
                    print(f"Steady-state elapsed {minute + 1}/60 minutes", flush=True)
                ended = started + timedelta(seconds=3600)
                time.sleep(10)
                history = []
                with httpx.Client(base_url=base, timeout=10) as client:
                    for device in ("CHG-001", "CHG-002", "CHG-003"):
                        response = client.get(
                            f"/api/devices/{device}/telemetry",
                            params={
                                "from": (started - timedelta(seconds=5)).isoformat(),
                                "to": (ended + timedelta(seconds=10)).isoformat(),
                            },
                        )
                        response.raise_for_status()
                        history.extend(response.json()["data"])
                (output / "history.json").write_text(json.dumps(history, indent=2))
                (output / "resources.json").write_text(json.dumps(resource_samples, indent=2))
                api_report = asyncio.run(api_load(base, datetime.now(UTC), output))
                command = [
                    "docker",
                    "compose",
                    "-p",
                    ports["PROJECT"],
                    "-f",
                    str(ROOT / "deploy/compose.yaml"),
                ]
                log_text = subprocess.run(
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
                (output / "steady-window.log").write_text(log_text)
                acked = set(
                    re.findall(r"telemetry_puback device_id=\S+ message_id=([0-9a-f-]+)", log_text)
                )
                stored = {row["message_id"]: row for row in history}
                committed = dict(
                    re.findall(
                        r"telemetry_committed message_id=([0-9a-f-]+) device_id=\S+ committed_at=(\S+)",
                        log_text,
                    )
                )
                latencies = [
                    (
                        datetime.fromisoformat(ts)
                        - datetime.fromisoformat(stored[key]["sample_ts"])
                    ).total_seconds()
                    * 1000
                    for key, ts in committed.items()
                    if key in stored
                ]
                ratio = len(acked & stored.keys()) / len(acked) if acked else 0
                report = {
                    "window_seconds": 3600,
                    "drain_seconds": 10,
                    "started_at": started.isoformat(),
                    "ended_at": ended.isoformat(),
                    "puback_unique": len(acked),
                    "matched_unique": len(acked & stored.keys()),
                    "reception_ratio": ratio,
                    "telemetry_count": len(latencies),
                    "telemetry_p95_ms": percentile(latencies),
                    "latencies_ms": latencies,
                    "api": {
                        key: value for key, value in api_report.items() if key != "duration_ms"
                    },
                    "cold_start_seconds": float(ports["STARTUP_SECONDS"]),
                    "status": "PASS"
                    if ratio >= 0.99
                    and len(latencies) >= 1000
                    and percentile(latencies) <= 1000
                    and api_report["status"] == "PASS"
                    else "FAIL",
                }
                (output / "measurements.json").write_text(json.dumps(report, indent=2))
            finally:
                if browser.poll() is None:
                    browser.send_signal(signal.SIGTERM)
                browser_code = browser.wait(timeout=20)
                if browser_code:
                    raise RuntimeError("Browser capture failed; see browser.log")
    return 0 if report["status"] == "PASS" else 1


def verify_performance(directory, query_directory=None):
    report = json.loads((directory / "measurements.json").read_text())
    query_source = query_directory or directory
    api = json.loads((query_source / "api-load.json").read_text())
    browser = json.loads((directory / "browser-observed.json").read_text())
    logs = (directory / "steady-window.log").read_text()
    committed = dict(
        re.findall(
            r"telemetry_committed message_id=([0-9a-f-]+) device_id=\S+ committed_at=(\S+)", logs
        )
    )
    visible = []
    for key, seen in browser["observations"].items():
        if key in committed:
            delta = (
                datetime.fromisoformat(seen) - datetime.fromisoformat(committed[key])
            ).total_seconds() * 1000
            if delta >= 0:
                visible.append({"message_id": key, "latency_ms": delta})
        if len(visible) == 20:
            break
    checks = {
        "60_minute_window": report["window_seconds"] == 3600,
        "reception_ratio": report["reception_ratio"] >= 0.99,
        "telemetry_samples": report["telemetry_count"] >= 1000,
        "telemetry_p95": report["telemetry_p95_ms"] is not None
        and report["telemetry_p95_ms"] <= 1000,
        "api_samples": api["requests"] == 1000
        and len(api["duration_ms"]) == 1000
        and api["warmup"] == 50
        and api["concurrency"] == 10,
        "api_p95": percentile(api["duration_ms"]) <= 500,
        "api_errors": not api["errors"],
        "browser_visible": len(visible) == 20
        and sum(item["latency_ms"] <= 4000 for item in visible) >= 19,
        "browser_errors": not browser["errors"],
        "backend_errors": not any(
            token in logs
            for token in ("Traceback", "database is locked", "TELEMETRY_DATABASE_ERROR")
        ),
        "cold_start": report["cold_start_seconds"] <= 120,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "visible_samples": visible,
        "telemetry_p95_ms": report["telemetry_p95_ms"],
        "api_p95_ms": percentile(api["duration_ms"]),
        "original_api_p95_ms": report["api"]["p95_ms"],
        "query_source": str(query_source),
        "query_source_sha256": hashlib.sha256(
            (query_source / "api-load.json").read_bytes()
        ).hexdigest(),
        "reception_ratio": report["reception_ratio"],
        "source_sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("measurements.json", "browser-observed.json", "steady-window.log")
        },
    }


def cold_start(output):
    output.mkdir(parents=True)
    with stack(output) as ports:
        after_up = time.monotonic()
        base = "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"]
        with httpx.Client(base_url=base, timeout=5) as client:
            health = client.get("/api/health")
            devices = client.get("/api/devices")
            page = client.get("/")
        with (output / "browser.log").open("w") as log:
            browser = subprocess.Popen(
                ["node", str(ROOT / "frontend/scripts/hold.mjs")],
                env={**os.environ, "PERF_BASE_URL": base, "PERF_OUTPUT": str(output.resolve())},
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 20
                while not (output / "browser-ready").exists():
                    if browser.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Cold-start browser not ready")
                    time.sleep(0.1)
                elapsed = float(ports["STARTUP_SECONDS"]) + time.monotonic() - after_up
            finally:
                if browser.poll() is None:
                    browser.send_signal(signal.SIGTERM)
                browser_code = browser.wait(timeout=20)
                if browser_code:
                    raise RuntimeError("Browser capture failed; see browser.log")
        checks = {
            "health": health.status_code == 200
            and health.json()["data"]["db"] == "ready"
            and health.json()["data"]["mqtt"] == "ready",
            "three_devices": devices.status_code == 200 and len(devices.json()["data"]) == 3,
            "page": page.status_code == 200,
            "within_120_seconds": elapsed <= 120,
        }
        report = {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks,
            "cold_start_seconds": elapsed,
            "health": health.json(),
            "devices": devices.json(),
            "project": ports["PROJECT"],
        }
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["core", "resilience", "performance"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-performance", type=Path)
    parser.add_argument("--query-evidence", type=Path)
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.output.exists():
        print("Output directory already exists; use a new evidence directory.", file=sys.stderr)
        return 2
    try:
        subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            check=True,
            capture_output=True,
            timeout=15,
        )
        if args.suite == "performance" and not args.reuse_performance:
            code = stability(args.output.resolve())
            verified = verify_performance(args.output.resolve())
            (args.output / "verified-report.json").write_text(json.dumps(verified, indent=2))
            return max(code, 0 if verified["status"] == "PASS" else 1)
        args.output.mkdir(parents=True)
        (args.output / "environment.json").write_text(json.dumps(environment(), indent=2))
        if args.suite == "performance":
            verified = verify_performance(args.reuse_performance.resolve(), args.query_evidence)
            verified["source_evidence"] = str(args.reuse_performance)
            (args.output / "report.json").write_text(json.dumps(verified, indent=2))
            return 0 if verified["status"] == "PASS" else 1
        paths = (
            ["tests/unit", "tests/integration"]
            if args.suite == "core"
            else [
                "tests/integration/test_recovery.py",
                "tests/integration/test_mqtt_ingestion.py",
                "tests/integration/test_agent_workflow.py",
            ]
        )
        with (args.output / "pytest.log").open("w") as log:
            result = subprocess.run(
                ["uv", "run", "pytest", *paths, "-q", f"--junitxml={args.output}/backend.xml"],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        if result.returncode:
            (args.output / "report.json").write_text(
                json.dumps({"status": "FAIL", "pytest_exit_code": result.returncode})
            )
            return 1
        if args.suite == "resilience":
            if args.reuse_performance:
                measured = verify_performance(args.reuse_performance.resolve(), args.query_evidence)
            else:
                stability(args.output / "stability")
                measured = verify_performance(args.output / "stability")
            report = {
                "status": measured["status"],
                "recovery": "PASS",
                "stability": measured,
                "source_evidence": str(args.reuse_performance)
                if args.reuse_performance
                else "stability/",
            }
        else:
            from scripts.acceptance_contract import REQUIRED

            cases = list(ET.parse(args.output / "backend.xml").iter("testcase"))
            covered = {}
            for ac, names in REQUIRED.items():
                missing = [
                    name
                    for name in names
                    if not any(
                        case.attrib["name"] == name or case.attrib["name"].startswith(name + "[")
                        for case in cases
                    )
                ]
                covered[ac] = {
                    "status": "NOT_RUN"
                    if missing
                    else "FAIL"
                    if any(
                        any(child.tag in {"skipped", "failure", "error"} for child in case)
                        for case in cases
                        if any(
                            case.attrib["name"] == name
                            or case.attrib["name"].startswith(name + "[")
                            for name in names
                        )
                    )
                    else "PASS",
                    "scope": "backend automatic subassertions",
                    "required_tests": names,
                    "missing_tests": missing,
                }
            cold = cold_start(args.output / "cold-start")
            covered["AC-01"] = {
                "status": cold["status"],
                "scope": "isolated four-service cold start",
                "evidence": "cold-start/report.json",
            }
            report = {
                "status": "PASS"
                if all(value["status"] == "PASS" for value in covered.values())
                else "FAIL",
                "scope": "core automated backend contracts; full AC/UI/real-model gates are aggregated separately",
                "results": covered,
            }
        (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 1
    except (subprocess.SubprocessError, OSError, RuntimeError, httpx.HTTPError) as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "blocked.json").write_text(
            json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__, "message": str(exc)})
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
