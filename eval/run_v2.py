"""B01—B24 isolation, actual API/tool execution and evidence-bound human review."""

import argparse
import asyncio
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from pydantic import ValidationError
from sqlalchemy import select

from backend.app.agent.prompts import SYSTEM_PROMPT
from backend.app.agent.tools import schemas
from backend.app.api import json_data
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AgentRun, KnowledgeChunk, KnowledgeDocument
from eval.checks_v2 import automatic_checks
from eval.run import sha, summarize
from scripts.acceptance import environment
from tests.support.clock import FixedClock
from tests.support.fixtures import T0
from tests.support.fixtures_v2 import load_v2_dataset, prepare_knowledge, snapshot_business
from tests.support.resources import ROOT

CASES = ROOT / "eval/cases-v2.jsonl"


async def evaluate(case, repeat, settings, output):
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="charge-eval-v2-") as temp:
        isolated = settings.model_copy(
            update={
                "app_env": "eval",
                "mqtt_enabled": False,
                "database_url": f"sqlite+aiosqlite:///{temp}/case.db",
            }
        )
        app = create_app(isolated, clock=FixedClock(T0))
        runs, prelude_runs, reports = [], [], []
        async with app.router.lifespan_context(app):
            fixture = await load_v2_dataset(app, case["profile"], case["case_id"], repeat)
            knowledge_variant = None
            if case.get("knowledge_variant"):
                knowledge_variant = await prepare_knowledge(
                    app, case["knowledge_variant"], Path(temp) / "knowledge"
                )
            async with app.state.db.sessions() as session:
                rows = (
                    await session.execute(
                        select(KnowledgeDocument, KnowledgeChunk)
                        .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
                        .where(
                            KnowledgeDocument.current,
                            KnowledgeDocument.applicable_model == "SIM-CHG-V2",
                        )
                    )
                ).all()
                catalog = {
                    f"{d.source_id}@{d.version}#{c.chunk_id}": c.content_hash for d, c in rows
                }
            if case.get("delay_tool"):
                original = app.state.runner.executor.invoke

                async def delayed(name, args, context):
                    if name == case["delay_tool"]:
                        await asyncio.sleep(case["delay_seconds"])
                    return await original(name, args, context)

                app.state.runner.executor.invoke = delayed
            before = await snapshot_business(app.state.db)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://eval"
            ) as client:

                async def submit(question, step, patrol=False):
                    request_id = str(uuid5(NAMESPACE_URL, f"v2/{case['case_id']}/{repeat}/{step}"))
                    payload = (
                        {
                            "request_id": request_id,
                            "window_minutes": case.get("patrol_window_minutes", 30),
                        }
                        if patrol
                        else {
                            "request_id": request_id,
                            "question": question,
                            "allow_work_order": case["allow_work_order"],
                        }
                    )
                    response = await client.post(
                        "/api/patrols" if patrol else "/api/agent/runs", json=payload
                    )
                    response.raise_for_status()
                    accepted = response.json()["data"]
                    async with asyncio.timeout(96):
                        await asyncio.shield(app.state.scheduler.task)
                    response = await client.get("/api/agent/runs/" + accepted["run_id"])
                    response.raise_for_status()
                    record = response.json()["data"]
                    async with app.state.db.sessions() as session:
                        row = await session.get(AgentRun, accepted["run_id"])
                        record["messages"] = row.messages_json
                        record["model_metrics"] = row.model_metrics_json
                        record["usage_available"] = [
                            m.get("usage") is not None for m in row.model_metrics_json
                        ]
                    if patrol:
                        response = await client.get("/api/patrols/" + accepted["report_id"])
                        response.raise_for_status()
                        reports.append(response.json()["data"])
                    return record

                question = case["question"]
                prelude_ok = True
                if case.get("prelude_question"):
                    prelude = await submit(case["prelude_question"], "prelude")
                    prelude_runs.append(prelude)
                    refs = [r for r in prelude.get("answer_refs", []) if r["kind"] == "KB"]
                    prelude_ok = prelude["status"] == "completed" and bool(refs)
                    if refs:
                        ref = refs[0]
                        question += f"。上一任务的引用是 [KB:{ref['source_id']}@{ref['version']}#{ref['chunk_id']}]，数据引用是 [DATA:{ref['tool_call_id']}]。"
                runs.append(await submit(question, "main", case.get("entrypoint") == "patrol"))
            after = await snapshot_business(app.state.db)
            checks = automatic_checks(case, runs, before, after, catalog)
            if prelude_runs:
                checks["prelude_completed_with_actual_knowledge"] = prelude_ok
            if reports:
                checks["report_matches_run"] = all(
                    report["status"] == run["status"] for report, run in zip(reports, runs)
                )
                if case.get("required_error"):
                    checks["failed_report_no_invented_snapshot"] = all(
                        not r["snapshot_json"] for r in reports
                    )
        all_runs = prelude_runs + runs
        record = {
            "case": case,
            "repeat": repeat,
            "mode": settings.llm_mode,
            "status": "PENDING_REVIEW" if all(checks.values()) else "FAIL",
            "critical_errors": [
                name
                for name in (
                    "business_unchanged",
                    "no_write_tools",
                    "same_run_references",
                    "current_applicable_knowledge",
                )
                if not checks[name]
            ],
            "automatic_checks": checks,
            "automatic_pass": all(checks.values()),
            "fixture": fixture,
            "knowledge_variant": knowledge_variant,
            "knowledge_catalog": catalog,
            "before": before,
            "after": after,
            "runs": runs,
            "prelude_runs": prelude_runs,
            "reports": reports,
            "total_seconds": time.monotonic() - started,
            "model_seconds": sum(m["duration_ms"] for r in all_runs for m in r["model_metrics"])
            / 1000,
            "tool_seconds": sum(c["duration_ms"] or 0 for r in all_runs for c in r["tool_calls"])
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


def summarize_v2(directory, review_file):
    return summarize(
        directory, review_file, case_prefix="B", case_count=24, min_success=65, min_category=10
    )


def source_hashes():
    # Explicit public source directories only; never read credentials or app runtime volumes.
    paths = [
        p
        for directory in (
            "backend",
            "simulator",
            "frontend/src",
            "knowledge",
            "eval",
            "tests/support",
            "scripts",
        )
        for p in (ROOT / directory).rglob("*")
        if p.is_file() and p.suffix in {".py", ".sql", ".md", ".jsonl", ".ts", ".vue", ".css"}
    ]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(paths)}


async def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cases = [json.loads(line) for line in CASES.read_text().splitlines()]
    if args.case:
        selected = set(args.case.split(","))
        if selected - {c["case_id"] for c in cases}:
            raise ValueError("Unknown case IDs")
        cases = [c for c in cases if c["case_id"] in selected]
    manifest = {
        "kind": "acceptance" if not args.case and args.repeat == 3 else "diagnostic",
        "mode": args.mode,
        "repeat": args.repeat,
        "executed_at": datetime.now(UTC).isoformat(),
        "cases_sha256": sha(CASES.read_bytes()),
        "environment": environment(),
        "source_hashes": source_hashes(),
        "prompt_sha256": sha(SYSTEM_PROMPT.encode()),
        "schema_sha256": sha(json.dumps(schemas(True), sort_keys=True).encode()),
        "results": [],
    }

    def save():
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    unresolved = [c["case_id"] for c in cases if c["contract_status"] != "READY"]
    if unresolved:
        manifest.update(
            status="NOT_RUN", message="案例合同尚待澄清/冻结", unresolved_cases=unresolved
        )
        save()
        return 1
    try:
        settings = Settings(app_env="eval", mqtt_enabled=False, llm_mode=args.mode)
    except ValidationError:
        manifest.update(
            status="BLOCKED",
            message="缺少有效模型配置；本地配置LLM_BASE_URL、LLM_MODEL、LLM_API_KEY。执行0例。",
        )
        save()
        return 2
    manifest["model"] = {
        "id": settings.llm_model if args.mode == "real" else "fixture",
        "endpoint_protocol": "chat-completions",
        "temperature": "provider default (not overridden)",
        "max_output_tokens": "provider default (not overridden)",
    }
    manifest["settings"] = {
        name: getattr(settings, name)
        for name in (
            "agent_model_timeout_seconds",
            "agent_tool_timeout_seconds",
            "agent_total_timeout_seconds",
            "agent_cleanup_timeout_seconds",
        )
    }
    save()
    for case in cases:
        for repeat in range(1, args.repeat + 1):
            result = await evaluate(case, repeat, settings, output)
            manifest["results"].append(result)
            save()
            print(
                f"{case['case_id']} repeat={repeat}: automatic_pass={result['automatic_pass']}",
                flush=True,
            )
    if manifest["kind"] == "acceptance":
        summary, code = summarize_v2(output, None)
    else:
        passed = all(r["automatic_pass"] for r in manifest["results"])
        summary, code = (
            {
                "status": "PENDING_REVIEW" if passed else "FAIL",
                "scope": "diagnostic only; not the 72-case gate",
            },
            3 if passed else 1,
        )
    manifest.update(status=summary["status"], summary=summary)
    save()
    reviews = [
        {
            **{k: r[k] for k in ("case_id", "repeat")},
            "evidence_sha256": r["sha256"],
            "reviewer": None,
            "reviewed_at": None,
            "success": None,
            "critical_errors": [],
            "notes": "",
        }
        for r in manifest["results"]
    ]
    (output / "review-template.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=2))
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fixture", "real"], default="real")
    parser.add_argument("--repeat", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--case", help="Comma-separated diagnostic subset; never full acceptance")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summarize", type=Path)
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args()
    if args.summarize:
        report, code = summarize_v2(args.summarize, args.review_file)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(code)
    if args.output is None:
        parser.error("--output is required")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
