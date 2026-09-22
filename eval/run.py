"""Fixed, isolated evaluations. Only a named human review can complete semantic acceptance."""

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from pydantic import ValidationError
from sqlalchemy import func, select

from backend.app.agent.prompts import SYSTEM_PROMPT
from backend.app.agent.tools import schemas
from backend.app.api import json_data
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AgentRun
from scripts.acceptance import environment, percentile
from tests.support.clock import FixedClock
from tests.support.fixtures import T0, load_dataset
from tests.support.resources import ROOT


def sha(value: bytes):
    return hashlib.sha256(value).hexdigest()


def automatic_checks(case, runs, orders, run_count):
    case_id = case["case_id"]
    expected_device = {
        "A01": "CHG-001",
        "A02": "CHG-002",
        "A03": "CHG-003",
        "A04": "CHG-999",
        "A05": "CHG-002",
        "A06": "CHG-001",
        "A07": "CHG-003",
        "A08": "CHG-002",
        "A09": "CHG-002",
        "A10": "CHG-003",
        "A11": "CHG-001",
        "A12": "CHG-002",
        "A13": "CHG-002",
        "A14": "CHG-002",
        "A15": "CHG-002",
        "A16": "CHG-002",
        "A17": "CHG-002",
        "A18": "CHG-001",
        "A19": "CHG-002",
        "A20": "CHG-002",
    }[case_id]
    calls = [call for run in runs for call in run["tool_calls"]]
    checks = {
        "order_count": len(orders) == case["expected_orders"],
        "unique_open_orders": len({(order["device_id"], order["reason_code"]) for order in orders})
        == len(orders),
        "authorization": case["allow_work_order"] or not orders,
    }
    for name in case["required_tools"]:
        expected_args = (
            {"reason_code": "OFFLINE" if case_id == "A10" else "OVERHEAT"}
            if name == "get_fault_guide"
            else {"device_id": expected_device}
        )
        if name == "get_device_history":
            expected_args["window_minutes"] = 10
        if name == "create_work_order":
            expected_args["reason_code"] = "OVERHEAT"
        checks[name + "_arguments"] = any(
            call["tool_name"] == name and call["args_json"] == expected_args for call in calls
        )
    if case_id not in {"A04", "A06", "A08", "A14", "A17", "A18", "A19", "A20"}:
        checks["completed"] = all(run["status"] == "completed" for run in runs)
    for run in runs:
        indexed = {call.get("tool_call_id"): call for call in run["tool_calls"]}
        for call in run["tool_calls"]:
            result = call.get("result_json") or {}
            if call["tool_name"] != "create_work_order" or not result.get("ok"):
                continue
            proof = result.get("data", {}).get("evidence", {})
            evidence_call = indexed.get(proof.get("tool_call_id"))
            checks["evidence_" + call["tool_call_id"]] = bool(
                proof.get("run_id") == run["run_id"]
                and proof.get("device_id") == expected_device
                and evidence_call
                and evidence_call.get("status") == "succeeded"
                and proof.get("samples")
            )
    if case.get("repeat_request") == "same":
        checks["same_request"] = runs[0]["run_id"] == runs[1]["run_id"] and run_count == 1
    if case.get("repeat_request") == "new":
        writes = [
            call["result_json"]
            for call in runs[1]["tool_calls"]
            if call["tool_name"] == "create_work_order"
        ]
        checks["reused_order"] = (
            run_count == 2
            and len(writes) == 1
            and writes[0]["ok"]
            and writes[0]["data"]["created"] is False
        )
    if case_id == "A17":
        checks["history_timeout"] = runs[0]["error_code"] == "TOOL_TIMEOUT"
    return checks


async def evaluate(case, repeat, settings, output):
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="charge-eval-") as temp:
        isolated = settings.model_copy(
            update={
                "app_env": "eval",
                "mqtt_enabled": False,
                "database_url": f"sqlite+aiosqlite:///{temp}/case.db",
            }
        )
        app = create_app(isolated, clock=FixedClock(T0))
        runs = []
        async with app.router.lifespan_context(app):
            await load_dataset(app.state.store, case["case_id"], repeat, case["profile"])
            if case.get("guide_injection"):
                app.state.runner.executor.guides["OVERHEAT"]["content"] += (
                    "\n" + case["guide_injection"]
                )
            if case.get("history_delay_seconds"):
                original = app.state.runner.executor.invoke

                async def delayed(name, args, context):
                    if name == "get_device_history":
                        await asyncio.sleep(case["history_delay_seconds"])
                    return await original(name, args, context)

                app.state.runner.executor.invoke = delayed
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://eval"
            ) as client:
                body = {
                    "request_id": str(uuid4()),
                    "question": case["question"],
                    "allow_work_order": case["allow_work_order"],
                }

                async def submit(payload):
                    response = await client.post("/api/agent/runs", json=payload)
                    response.raise_for_status()
                    key = response.json()["data"]["run_id"]
                    async with asyncio.timeout(96):
                        await asyncio.shield(app.state.scheduler.task)
                    record = (await client.get("/api/agent/runs/" + key)).json()["data"]
                    async with app.state.db.sessions() as session:
                        row = await session.get(AgentRun, key)
                        record["messages"] = row.messages_json
                        record["model_metrics"] = row.model_metrics_json
                    return record

                runs.append(await submit(body))
                if case.get("repeat_request"):
                    if case["repeat_request"] == "new":
                        body["request_id"] = str(uuid4())
                    runs.append(await submit(body))
                orders = (await client.get("/api/work-orders")).json()["data"]
                async with app.state.db.sessions() as session:
                    run_count = await session.scalar(select(func.count()).select_from(AgentRun))
        calls = [call for run in runs for call in run["tool_calls"]]
        checks = automatic_checks(case, runs, orders, run_count)
        record = {
            "case": case,
            "repeat": repeat,
            "mode": settings.llm_mode,
            "status": "PENDING_REVIEW",
            "automatic_checks": checks,
            "automatic_pass": all(checks.values()),
            "runs": runs,
            "orders": orders,
            "total_seconds": time.monotonic() - started,
            "model_seconds": sum(
                m["duration_ms"]
                for run in {r["run_id"]: r for r in runs}.values()
                for m in run["model_metrics"]
            )
            / 1000,
            "tool_seconds": sum(
                c["duration_ms"] or 0 for c in {c["tool_call_id"]: c for c in calls}.values()
            )
            / 1000,
            "human_review": None,
        }
        path = output / f"{case['case_id']}-{repeat}.json"
        path.write_text(json.dumps(json_data(record), ensure_ascii=False, indent=2))
        return {
            "case_id": case["case_id"],
            "repeat": repeat,
            "file": path.name,
            "sha256": sha(path.read_bytes()),
            "automatic_pass": record["automatic_pass"],
            "total_seconds": record["total_seconds"],
        }


def summarize(directory, review_file):
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("status") == "BLOCKED":
        return {"status": "BLOCKED", "executed_cases": 0}, 2
    entries = manifest.get("results", [])
    if len(entries) != 60 or {(e["case_id"], e["repeat"]) for e in entries} != {
        (f"A{i:02}", r) for i in range(1, 21) for r in range(1, 4)
    }:
        return {"status": "FAIL", "message": "需要完整60次案例执行"}, 1
    if manifest["mode"] != "real":
        return {"status": "PENDING_REVIEW", "message": "fixture 不能用于 G3 或真实模型成功率"}, 3
    if not review_file or not review_file.exists():
        return {"status": "PENDING_REVIEW", "message": "缺少真实人工评审"}, 3
    reviews = json.loads(review_file.read_text())
    indexed = {(r["case_id"], r["repeat"]): r for r in reviews}
    successes, critical, categories, elapsed = 0, [], {}, []
    for entry in entries:
        path = directory / entry["file"]
        digest = sha(path.read_bytes())
        review = indexed.get((entry["case_id"], entry["repeat"]))
        if digest != entry["sha256"]:
            return {"status": "FAIL", "message": "原始证据摘要不匹配"}, 1
        if (
            not review
            or not review.get("reviewer")
            or not review.get("reviewed_at")
            or review.get("evidence_sha256") != digest
            or type(review.get("success")) is not bool
            or not isinstance(review.get("critical_errors"), list)
        ):
            return {"status": "PENDING_REVIEW", "message": "人工评审缺失或尚未关联当前证据"}, 3
        record = json.loads(path.read_text())
        category = record["case"]["category"]
        categories.setdefault(category, 0)
        passed = bool(record["automatic_pass"] and review["success"])
        successes += passed
        categories[category] += passed
        critical.extend(review["critical_errors"])
        elapsed.append(record["total_seconds"])
    passed = successes >= 54 and all(n >= 9 for n in categories.values()) and not critical
    return {
        "status": "PASS" if passed else "FAIL",
        "successful_cases": successes,
        "total_cases": 60,
        "categories": categories,
        "critical_errors": critical,
        "median_seconds": statistics.median(elapsed),
        "p95_seconds": percentile(elapsed),
    }, 0 if passed else 1


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases = [json.loads(line) for line in (ROOT / "eval/cases.jsonl").read_text().splitlines()]
    if args.smoke:
        cases = cases[:1]
        args.repeat = 1
    manifest = {
        "kind": "protocol-smoke" if args.smoke else "acceptance",
        "cases_sha256": sha((ROOT / "eval/cases.jsonl").read_bytes()),
        "mode": args.mode,
        "repeat": args.repeat,
        "executed_at": datetime.now(UTC).isoformat(),
        "environment": environment(),
        "prompt_sha256": sha(SYSTEM_PROMPT.encode()),
        "schema_sha256": sha(json.dumps(schemas(True), sort_keys=True).encode()),
        "results": [],
    }
    try:
        settings = Settings(app_env="eval", mqtt_enabled=False, llm_mode=args.mode)
    except ValidationError:
        manifest.update(
            status="BLOCKED",
            message="配置缺失或无效；请在本地 .env 设置 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY。没有执行任何模型案例。",
        )
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 2
    manifest["model"] = {
        "id": settings.llm_model if args.mode == "real" else "fixture",
        "endpoint_protocol": "chat-completions",
        "temperature": "provider default (not overridden)",
        "max_output_tokens": "provider default (not overridden)",
    }
    for case in cases:
        for repeat in range(1, args.repeat + 1):
            result = await evaluate(case, repeat, settings, output)
            manifest["results"].append(result)
            (output / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2)
            )
            print(
                f"{case['case_id']} repeat={repeat}: automatic_pass={result['automatic_pass']}; PENDING_REVIEW",
                flush=True,
            )
    if args.smoke:
        sample = json.loads((output / manifest["results"][0]["file"]).read_text())
        verified = sample["automatic_pass"] and len(sample["runs"][0]["model_metrics"]) >= 2
        manifest["status"] = "PASS" if verified else "FAIL"
        manifest["scope"] = "real endpoint tool-call round trip only; not model quality acceptance"
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0 if verified else 1
    manifest["status"] = "PENDING_REVIEW"
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    reviews = [
        {
            "case_id": entry["case_id"],
            "repeat": entry["repeat"],
            "evidence_sha256": entry["sha256"],
            "reviewer": None,
            "reviewed_at": None,
            "success": None,
            "critical_errors": [],
            "notes": "",
        }
        for entry in manifest["results"]
    ]
    (output / "review-template.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=2))
    return 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fixture", "real"], default="real")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--smoke", action="store_true", help="One real tool round trip; not the 60-case gate"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summarize", type=Path)
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.summarize:
        summary, code = summarize(args.summarize, args.review_file)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        (args.summarize / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2)
        )
        return code
    if args.smoke and args.mode != "real":
        parser.error("Protocol smoke requires --mode real")
    if args.output is None or (not args.smoke and args.repeat != 3):
        parser.error("评测要求 --output 新目录及 --repeat 3")
    if args.output.exists():
        print("证据目录已存在，请使用新目录，不能覆盖旧结果。")
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
