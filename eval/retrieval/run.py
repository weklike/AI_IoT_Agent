"""Isolated retrieval comparison using immutable query/source labels; no model calls."""

import argparse
import asyncio
import hashlib
import json
import math
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Device

ROOT = Path(__file__).resolve().parents[2]


async def evaluate(dataset: Path, output: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((dataset.parent / "manifest.json").read_text())
    for name, digest in frozen["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen source or labels changed: " + name)
    cases = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    acceptance = dataset.name == "test.jsonl"
    if acceptance and (len(cases) != 32 or sum(not row["expect_empty"] for row in cases) != 24):
        raise ValueError("Acceptance requires 24 positive and 8 negative queries")
    records = []
    with tempfile.TemporaryDirectory(prefix="charge-retrieval-") as directory:
        app = create_app(
            Settings(
                _env_file=None,
                app_env="eval",
                mqtt_enabled=False,
                llm_mode="fixture",
                database_url=f"sqlite+aiosqlite:///{directory}/eval.db",
            )
        )
        async with app.router.lifespan_context(app):
            for case in cases:
                async with app.state.db.sessions.begin() as session:
                    device = await session.get(Device, case["device_id"])
                    device.model = case.get("model_override") or "SIM-CHG-V2"
                for method in ("exact_tags", "fts5"):
                    began = time.perf_counter()
                    matches = (
                        await app.state.knowledge.search(
                            case["query"], case["device_id"], method=method
                        )
                    )["matches"]
                    duration = (time.perf_counter() - began) * 1000
                    relevant = {
                        (row["source_id"], row["version"], row["content_hash"])
                        for row in case["relevant"]
                    }
                    ranks = [
                        index
                        for index, row in enumerate(matches, 1)
                        if (row["source_id"], row["version"], row["hash"]) in relevant
                    ]
                    records.append(
                        {
                            "query_id": case["query_id"],
                            "query": case["query"],
                            "method": method,
                            "expect_empty": case["expect_empty"],
                            "matches": matches,
                            "duration_ms": duration,
                            "hit": bool(ranks),
                            "reciprocal_rank": 1 / min(ranks) if ranks else 0,
                            "empty_correct": not matches if case["expect_empty"] else None,
                        }
                    )
    summaries = {}
    for method in ("exact_tags", "fts5"):
        rows = [row for row in records if row["method"] == method]
        positive = [row for row in rows if not row["expect_empty"]]
        negative = [row for row in rows if row["expect_empty"]]
        durations = sorted(row["duration_ms"] for row in rows)
        summaries[method] = {
            "positive_count": len(positive),
            "hits": sum(row["hit"] for row in positive),
            "hit_at_5": sum(row["hit"] for row in positive) / len(positive),
            "mrr_at_5": sum(row["reciprocal_rank"] for row in positive) / len(positive),
            "negative_count": len(negative),
            "negative_correct": sum(row["empty_correct"] for row in negative),
            "p95_ms": durations[math.ceil(len(durations) * 0.95) - 1],
        }
    actual = summaries["fts5"]
    passed = (
        not acceptance
        or actual["hits"] >= 22
        and actual["mrr_at_5"] >= 0.80
        and actual["negative_correct"] == 8
    )
    report = {
        "status": "PASS" if passed else "FAIL",
        "acceptance_evaluated": acceptance,
        "dataset": str(dataset),
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "executed_at": datetime.now(UTC).isoformat(),
        "summaries": summaries,
        "records": records,
    }
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (output / "frozen-manifest.json").write_text(
        json.dumps(frozen, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "acceptance_evaluated": acceptance,
                "summaries": summaries,
            },
            ensure_ascii=False,
        )
    )
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(evaluate(args.dataset, args.output))


if __name__ == "__main__":
    raise SystemExit(main())
