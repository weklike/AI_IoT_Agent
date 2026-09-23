"""Twenty actual mixed decrease/increase plans with independently reconstructed bounds."""

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import httpx

from scripts.acceptance import environment
from scripts.stability_v2 import Exercise
from tests.support.resources import stack


def assess_plan(plan, commands, states, elapsed):
    old = {
        device: value["power_limit_w"]
        for device, value in plan["snapshot_json"]["fingerprint"].items()
    }
    targets = plan["allocation_json"]
    lower = {d for d in old if targets[d] < old[d]}
    higher = {d for d in old if targets[d] > old[d]}
    protection = max(plan["budget_w"], plan["snapshot_json"]["confirmed_budget_w"])
    changed = lower | higher
    checks = {
        "mixed_decrease_increase": bool(lower and higher),
        "all_commands_recorded": set(commands) == changed,
        "within_30_plus_5_seconds": elapsed <= 35,
        "complete_verified": plan["status"] == "VERIFIED",
        "decreases_verified_before_increases": True,
        "upper_bound_safe": True,
        "fresh_targets": True,
    }
    events = []
    verified = {}
    for device, command in commands.items():
        result = command.get("verification_json")
        valid = (
            command["status"] == "applied"
            and command["verification_status"] == "verified"
            and result
            and result.get("message_id")
        )
        checks["complete_verified"] &= bool(valid)
        target = command["args_json"]["power_limit_w"]
        checks["complete_verified"] &= target == targets[device]
        sent = datetime.fromisoformat(command["issued_at"])
        events.append((sent, 1, device, target, "sent"))
        if valid:
            at = datetime.fromisoformat(result["checked_at"])
            verified[device] = at
            events.append((at, 0, device, target, "verified"))
        current = states.get(device, {})
        checks["fresh_targets"] &= bool(
            current.get("data_fresh")
            and current.get("power_limit_w") == targets[device]
            and current.get("applied_control_generation", -1) >= command["generation"]
        )
    for device in higher:
        if device not in commands:
            checks["decreases_verified_before_increases"] = False
            continue
        sent = datetime.fromisoformat(commands[device]["issued_at"])
        checks["decreases_verified_before_increases"] &= all(
            d in verified and verified[d] <= sent for d in lower
        )
    bounds = dict(old)
    history = []
    for at, _, device, target, event in sorted(events):
        bounds[device] = target if event == "verified" else max(bounds[device], target)
        if event == "sent" and device in higher:
            checks["upper_bound_safe"] &= sum(bounds.values()) <= protection
        history.append(
            {
                "at": at.isoformat(),
                "device_id": device,
                "event": event,
                "bounds_w": dict(bounds),
                "total_upper_w": sum(bounds.values()),
                "protection_w": protection,
            }
        )
    return {"checks": checks, "upper_bound_events": history, "elapsed_seconds": elapsed}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plans", type=int, choices=[2, 20], default=20)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        print("Evidence directory exists; choose another path")
        return 2
    output.mkdir(parents=True)
    (output / "environment.json").write_text(json.dumps(environment(), indent=2))
    records = []
    try:
        with stack(output, operations=True) as ports:
            base = "http://127.0.0.1:" + ports["FRONTEND_PUBLISH_PORT"]
            with httpx.Client(base_url=base, timeout=10) as client:
                exercise = Exercise(client, output)
                deadline = time.monotonic() + 15
                while True:
                    states = exercise.request("GET", "/api/devices")
                    if len(states) == 3 and all(
                        s["data_fresh"] and s["schema_version"] == 2 for s in states
                    ):
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError("Fresh operations samples unavailable")
                    time.sleep(0.2)
                for device in ("CHG-001", "CHG-002", "CHG-003"):
                    exercise.start(device)
                initial = exercise.plan(45000, "equal", -1)
                if initial["status"] != "VERIFIED":
                    raise RuntimeError("Initial equal plan not verified")
                from uuid import uuid4

                orders = [
                    ["CHG-001", "CHG-002", "CHG-003"],
                    ["CHG-002", "CHG-003", "CHG-001"],
                    ["CHG-003", "CHG-001", "CHG-002"],
                ]
                for index in range(args.plans):
                    record = {"index": index, "status": "NOT_RUN"}
                    records.append(record)
                    (output / "plans.json").write_text(json.dumps(records, indent=2))
                    preview = exercise.request(
                        "POST",
                        "/api/power-plans",
                        {
                            "request_id": str(uuid4()),
                            "budget_w": 45000,
                            "strategy": "priority",
                            "device_priority": orders[index % 3],
                        },
                    )
                    record["preview"] = preview
                    tick = time.monotonic()
                    record["accepted"] = exercise.request(
                        "POST",
                        f"/api/power-plans/{preview['plan_id']}/execute",
                        {"request_id": str(uuid4())},
                    )
                    plan = exercise.wait(
                        "/api/power-plans/" + preview["plan_id"],
                        lambda r: r["status"] not in {"PREVIEW", "EXECUTING"},
                        36,
                    )
                    elapsed = time.monotonic() - tick
                    commands = {
                        d: exercise.request("GET", "/api/device-commands/" + c["command_id"])
                        for d, c in plan["commands"].items()
                    }
                    states = {
                        row["device_id"]: row for row in exercise.request("GET", "/api/devices")
                    }
                    record.update(
                        plan=plan,
                        commands=commands,
                        states=states,
                        assessment=assess_plan(plan, commands, states, elapsed),
                    )
                    record["status"] = (
                        "PASS" if all(record["assessment"]["checks"].values()) else "FAIL"
                    )
                    (output / "plans.json").write_text(
                        json.dumps(records, ensure_ascii=False, indent=2)
                    )
                    print(f"Mixed plan {index + 1}/{args.plans}: {record['status']}", flush=True)
                    if plan["status"] != "VERIFIED":
                        break
        passed = len(records) == args.plans and all(r["status"] == "PASS" for r in records)
        report = {
            "status": "PASS" if passed else "FAIL",
            "kind": "acceptance" if args.plans == 20 else "diagnostic",
            "requested_plans": args.plans,
            "executed_plans": len(records),
            "passed_plans": sum(r["status"] == "PASS" for r in records),
            "evidence": "plans.json",
        }
        (output / "report.json").write_text(json.dumps(report, indent=2))
        return 0 if passed else 1
    except (OSError, subprocess.SubprocessError, RuntimeError, httpx.HTTPError) as error:
        status = "FAIL" if (output / "operations.json").exists() else "BLOCKED"
        (output / "failure.json").write_text(
            json.dumps(
                {"status": status, "error_type": type(error).__name__, "message": str(error)},
                indent=2,
            )
        )
        return 1 if status == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
