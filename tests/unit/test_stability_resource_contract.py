import json
from datetime import timedelta

from scripts.stability_v2 import resource_sample, summarize_window


def test_resource_count_alone_cannot_replace_required_cpu_rss_measurements(tmp_path, fixed_now):
    (tmp_path / "browser-observed.json").write_text(json.dumps({"errors": [], "observations": []}))
    resources = [
        {
            "runtime": {
                "guardians": {"mqtt-consumer": 1, "alarm-timer": 1, "patrol-timer": 1},
                "managed": {"charging": 0, "power": 0, "scenario": 0, "scripts": 0, "agent": 0},
            },
            "states": [],
            "containers": [],
            "volumes": {},
        }
    ]
    result = summarize_window(
        tmp_path, fixed_now, fixed_now + timedelta(minutes=1), [], "", resources, [], 1
    )
    assert result["checks"]["resource_samples"] is False


def test_resource_sampler_records_process_rss_separately_from_docker_memory(monkeypatch):
    from types import SimpleNamespace

    def run(command, **kwargs):
        if command[1] == "stats":
            output = "\n".join(
                json.dumps({"Name": name, "CPUPerc": "1.2%", "MemUsage": "90MiB / 1GiB"})
                for name in command[6:]
            )
        elif command[1] == "inspect":
            output = json.dumps(
                [
                    {"Name": name, "State": {"Status": "running"}, "RestartCount": 0}
                    for name in command[2:]
                ]
            )
        elif command[1] == "top":
            assert command[3:] == ["-eo", "pid,ppid,rss,comm"]
            output = "PID PPID RSS COMMAND\n101 1 12345 uvicorn\n102 101 2345 worker\n"
        else:
            output = json.dumps({"total_bytes": 4096, "files_bytes": {"state": 4096}})
        return SimpleNamespace(stdout=output)

    monkeypatch.setattr("scripts.stability_v2.subprocess.run", run)
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {})
    result = resource_sample("owned-project", SimpleNamespace(get=lambda path: response), 1)
    assert set(result["rss_processes"]) == {"backend", "simulator", "mqtt", "frontend"}
    for rows in result["rss_processes"].values():
        assert [r["rss_kib"] for r in rows] == [12345, 2345]
        assert [r["pid"] for r in rows] == [101, 102]
