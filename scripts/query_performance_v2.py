"""Separate-process HTTP measurements of actual four-service query endpoints."""

import argparse
import asyncio
import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from scripts.acceptance import environment, percentile
from tests.support.resources import ROOT, stack


async def measure(base, anchor, output):
    window = {"from": (anchor - timedelta(hours=1)).isoformat(), "to": anchor.isoformat()}
    groups = [
        ("fleet", "/api/fleet-overview", {"window_minutes": 60}),
        ("sessions", "/api/charging-sessions", {**window, "device_id": "CHG-002"}),
        ("statistics", "/api/charging-statistics", {**window, "device_id": "CHG-002"}),
        ("timeline", "/api/devices/CHG-002/timeline", window),
    ]
    rows, warmup = [], []
    async with httpx.AsyncClient(base_url=base, timeout=10) as client:

        async def request(index, destination):
            name, path, params = groups[index % 4]
            started = time.monotonic()
            row = {"index": index, "group": name}
            try:
                response = await client.get(path, params=params)
                row.update(http_status=response.status_code, ok=response.status_code == 200)
            except httpx.HTTPError as error:
                row.update(error=type(error).__name__, ok=False)
            row["duration_ms"] = (time.monotonic() - started) * 1000
            destination.append(row)

        for i in range(50):
            await request(i, warmup)

        async def worker(offset):
            for index in range(offset, 1000, 10):
                await request(index, rows)

        await asyncio.gather(*(worker(i) for i in range(10)))
    summaries = {
        name: {
            "requests": sum(r["group"] == name for r in rows),
            "p95_ms": percentile([r["duration_ms"] for r in rows if r["group"] == name]),
            "errors": sum(not r["ok"] for r in rows if r["group"] == name),
        }
        for name, _, _ in groups
    }
    p95 = percentile([r["duration_ms"] for r in rows])
    passed = (
        len(rows) == 1000
        and all(r["ok"] for r in rows + warmup)
        and p95 <= 500
        and all(s["p95_ms"] <= 500 and s["requests"] == 250 for s in summaries.values())
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "warmup": warmup,
        "concurrency": 10,
        "requests": sorted(rows, key=lambda r: r["index"]),
        "groups": summaries,
        "p95_ms": p95,
        "threshold_ms": 500,
    }
    (output / "query-load.json").write_text(json.dumps(report, indent=2))
    return {k: v for k, v in report.items() if k not in {"requests", "warmup"}}


async def knowledge_load(base, output):
    cases = [
        json.loads(line) for line in (ROOT / "eval/retrieval/test.jsonl").read_text().splitlines()
    ]
    rows, warmup = [], []
    async with httpx.AsyncClient(base_url=base, timeout=10) as client:
        for index in range(220):
            case = cases[(index - 20) % 32] if index >= 20 else cases[index % 32]
            params = {"query": case["query"]}
            if case.get("device_id"):
                params["device_id"] = case["device_id"]
            started = time.monotonic()
            row = {"query_id": case["query_id"], "index": index - 20}
            try:
                response = await client.get("/api/knowledge/search", params=params)
                row.update(
                    http_status=response.status_code,
                    ok=response.status_code == 200,
                    response=response.json(),
                )
            except httpx.HTTPError as error:
                row.update(error=type(error).__name__, ok=False)
            row["duration_ms"] = (time.monotonic() - started) * 1000
            (rows if index >= 20 else warmup).append(row)
    p95 = percentile([r["duration_ms"] for r in rows])
    report = {
        "status": "PASS" if p95 <= 300 and all(r["ok"] for r in rows + warmup) else "FAIL",
        "p95_ms": p95,
        "threshold_ms": 300,
        "requests": rows,
        "warmup": warmup,
        "query_order_sha256": __import__("hashlib")
        .sha256((ROOT / "eval/retrieval/test.jsonl").read_bytes())
        .hexdigest(),
    }
    (output / "knowledge-load.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return {k: v for k, v in report.items() if k not in {"requests", "warmup"}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "environment.json").write_text(json.dumps(environment(), indent=2))
    try:
        with stack(output, simulator=False, operations=True) as ports:
            seeded = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-e",
                    "APP_ENV=test",
                    f"{ports['PROJECT']}-backend-1",
                    "/app/.venv/bin/python",
                    "-m",
                    "tests.support.query_dataset_v2",
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            dataset = json.loads(seeded.stdout)
            (output / "dataset.json").write_text(json.dumps(dataset, indent=2))
            base = "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"]
            queries = asyncio.run(measure(base, datetime.fromisoformat(dataset["anchor"]), output))
            knowledge = asyncio.run(knowledge_load(base, output))
            report = {
                "status": "PASS" if queries["status"] == knowledge["status"] == "PASS" else "FAIL",
                "queries": queries,
                "knowledge": knowledge,
            }
            code = 0 if report["status"] == "PASS" else 1
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        report = {
            "status": "BLOCKED",
            "error": type(error).__name__,
            "message": "测试环境未完成；保留日志并使用新输出目录重跑",
        }
        code = 2
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
