import json
import subprocess
import time
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from tests.support.resources import stack


def test_operations_broker_gap_preserves_energy_without_fabricated_telemetry(tmp_path, request):
    def wait(predicate, seconds=10):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            result = predicate()
            if result:
                return result
            time.sleep(0.1)
        raise AssertionError("Expected actual feedback before deadline")

    with stack(tmp_path / "logs", operations=True) as ports:
        with httpx.Client(
            base_url="http://127.0.0.1:" + ports["BACKEND_PUBLISH_PORT"], timeout=3
        ) as client:

            def get(path, **params):
                response = client.get(path, params=params)
                response.raise_for_status()
                return response.json()["data"]

            def post(path, **body):
                response = client.post(path, json={"request_id": str(uuid4()), **body})
                response.raise_for_status()
                return response.json()["data"]

            wait(
                lambda: all(
                    x["status"]["data_fresh"]
                    for x in get("/api/fleet-overview", window_minutes=10)["devices"]
                )
            )
            started = post("/api/devices/CHG-001/charging/start", requested_power_w=20000)
            wait(
                lambda: (
                    get("/api/device-commands/" + started["command_id"])["verification_status"]
                    == "verified"
                )
            )
            plan = post("/api/power-plans", budget_w=20000, strategy="equal")
            post("/api/power-plans/" + plan["plan_id"] + "/execute")
            wait(lambda: get("/api/power-plans/" + plan["plan_id"])["status"] == "VERIFIED")
            before = get("/api/devices/CHG-001")
            assert before["power_kw"] == 20
            broker = ports["PROJECT"] + "-mqtt-1"
            subprocess.run(["docker", "stop", broker], check=True, capture_output=True, timeout=20)
            gap_start = datetime.now(UTC)
            time.sleep(10)
            gap_end = datetime.now(UTC)
            subprocess.run(["docker", "start", broker], check=True, capture_output=True, timeout=20)
            recovered = wait(
                lambda: (
                    row
                    if (row := get("/api/devices/CHG-001"))["message_id"] != before["message_id"]
                    and row["data_fresh"]
                    else None
                )
            )
            assert recovered["session_id"] == started["session_id"]
            assert recovered["meter_total_wh"] - before["meter_total_wh"] >= 55
            assert recovered["session_energy_wh"] - before["session_energy_wh"] >= 55
            stopped = post("/api/devices/CHG-001/charging/stop", session_id=started["session_id"])
            wait(
                lambda: (
                    get("/api/device-commands/" + stopped["command_id"])["verification_status"]
                    == "verified"
                )
            )
            session = get("/api/charging-sessions/" + started["session_id"])
            assert session["status"] == "COMPLETED"
            assert session["energy_wh"] == session["end_meter_wh"] - session["start_meter_wh"]
            assert session["energy_wh"] >= recovered["session_energy_wh"]
            history = get(
                "/api/devices/CHG-001/telemetry",
                **{"from": gap_start.isoformat(), "to": gap_end.isoformat()},
            )
            assert history == []
            request.node.user_properties.append(
                (
                    "broker_gap_evidence",
                    json.dumps(
                        {
                            "before": before,
                            "after": recovered,
                            "session": session,
                            "gap_start": gap_start.isoformat(),
                            "gap_end": gap_end.isoformat(),
                        },
                        ensure_ascii=False,
                    ),
                )
            )
