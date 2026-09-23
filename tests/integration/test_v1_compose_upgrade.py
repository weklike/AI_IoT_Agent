import json
import os
import sqlite3
import subprocess
import time
from uuid import uuid4

import httpx

from tests.support.resources import ROOT, free_port


def test_owned_four_services_upgrade_v1_copy_and_keep_original_evidence(tmp_path, request):
    project = "charge-upgrade-" + uuid4().hex[:12]
    data = tmp_path / "owned-data"
    data.mkdir()
    database = data / "charge_ops.db"
    with sqlite3.connect(database) as con:
        con.executescript((ROOT / "tests/fixtures/v1_schema.sql").read_text())
        con.execute("INSERT INTO devices(device_id,name) VALUES ('CHG-001','legacy-device')")
        con.execute(
            "INSERT INTO telemetry VALUES (1,?,'CHG-001',?,1,1,'2026-09-22T08:10:00.000000Z','2026-09-22T08:10:00.000000Z',72,400,50,20,'charging')",
            (str(uuid4()), str(uuid4())),
        )
        con.execute(
            "INSERT INTO agent_runs VALUES ('legacy-run','legacy-request','hash','legacy-question',1,'completed','legacy-answer','2026-09-22T08:10:00.000000Z',NULL,NULL,'[]','[]')"
        )
        con.execute(
            "INSERT INTO tool_calls VALUES ('legacy-tool','legacy-provider',1,'legacy-run','get_device_status','{}','{\"sample_id\":1}','succeeded','2026-09-22T08:10:00.000000Z',1,NULL)"
        )
        con.execute(
            "INSERT INTO work_orders VALUES ('legacy-order','CHG-001','OVERHEAT','OPEN','{\"tool_call_id\":\"legacy-tool\",\"sample_id\":1}','legacy-run','2026-09-22T08:10:00.000000Z')"
        )
        tables = {
            name: [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
            for name in ("telemetry", "agent_runs", "tool_calls", "work_orders")
        }
        expected = {
            name: con.execute(f"SELECT {','.join(columns)} FROM {name}").fetchone()
            for name, columns in tables.items()
        }
        con.commit()
    # The host writer is now closed; only the owned container accesses this copy.
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    override = tmp_path / "override.json"
    override.write_text(
        json.dumps(
            {
                "services": {
                    "backend": {
                        "environment": {"APP_ENV": "test"},
                        "volumes": [{"type": "bind", "source": str(data), "target": "/data"}],
                    }
                }
            }
        )
    )
    env = {
        **os.environ,
        "MQTT_PUBLISH_PORT": str(free_port()),
        "BACKEND_PUBLISH_PORT": str(free_port()),
        "FRONTEND_PUBLISH_PORT": str(free_port()),
        "MQTT_TOPIC_PREFIX": project + "/v1",
        "BACKEND_IMAGE": "charge-ops-backend:" + project,
        "FRONTEND_IMAGE": "charge-ops-frontend:" + project,
        "SIMULATOR_MODE": "operations",
        "LLM_MODE": "fixture",
        "LLM_MODEL": "",
        "LLM_API_KEY": "",
        "LLM_BASE_URL": "",
        "LLM_DOCKER_BASE_URL": "",
    }
    command = [
        "docker",
        "compose",
        "--env-file",
        str(empty_env),
        "-p",
        project,
        "-f",
        str(ROOT / "deploy/compose.yaml"),
        "-f",
        str(override),
    ]
    try:
        subprocess.run(command + ["build"], env=env, check=True, capture_output=True, timeout=300)
        began = time.monotonic()
        subprocess.run(
            command + ["up", "-d", "--wait", "--wait-timeout", "120"],
            env=env,
            check=True,
            capture_output=True,
            timeout=150,
        )
        with httpx.Client(
            base_url="http://127.0.0.1:" + env["FRONTEND_PUBLISH_PORT"], timeout=5
        ) as client:
            assert client.get("/api/health").status_code == 200
            response = client.get(
                "/api/knowledge/search", params={"query": "过温", "device_id": "CHG-001"}
            )
            assert response.status_code == 200 and response.json()["data"]["matches"]
        elapsed = time.monotonic() - began
        assert elapsed <= 120
        read_code = """
import sqlite3,json,sys
tables=json.loads(sys.argv[1]); expected=json.loads(sys.argv[2])
with sqlite3.connect('file:/data/charge_ops.db?mode=ro',uri=True) as db:
    rows={name:db.execute('SELECT '+','.join(columns)+' FROM '+name+' WHERE '+columns[0]+'=?',(expected[name][0],)).fetchone() for name,columns in tables.items()}
    print(json.dumps({'rows':rows,'fk':db.execute('PRAGMA foreign_key_check').fetchall(),'migrations':db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],'v2_empty':db.execute('SELECT session_id,power_limit_w,meter_total_wh FROM telemetry WHERE id=1').fetchone()}))
"""
        result = subprocess.run(
            [
                "docker",
                "exec",
                project + "-backend-1",
                "/app/.venv/bin/python",
                "-c",
                read_code,
                json.dumps(tables),
                json.dumps(expected),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        actual = json.loads(result.stdout)
        assert actual["rows"] == json.loads(json.dumps(expected))
        assert actual["fk"] == [] and actual["migrations"] == 7
        assert actual["v2_empty"] == [None, None, None]
        request.node.user_properties.append(
            (
                "upgrade_evidence",
                json.dumps({"startup_seconds": elapsed, **actual}, ensure_ascii=False),
            )
        )
    finally:
        logs = subprocess.run(
            command + ["logs", "--no-color"], env=env, capture_output=True, text=True, timeout=20
        )
        (tmp_path / "compose.log").write_text(logs.stdout + logs.stderr)
        subprocess.run(
            command + ["down", "-v", "--remove-orphans"],
            env=env,
            check=True,
            capture_output=True,
            timeout=60,
        )
