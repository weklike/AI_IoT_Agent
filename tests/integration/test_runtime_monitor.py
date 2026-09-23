import asyncio

import httpx
import pytest

from tests.integration.test_eval_v2_fixtures import app as app
from tests.support.monitor_app import create_test_app, runtime_state


async def test_runtime_counts_real_guardians_and_normal_app_has_no_test_route(app):
    result = runtime_state(app)
    assert result["guardians"] == {"mqtt-consumer": 1, "alarm-timer": 1, "patrol-timer": 1}
    assert result["managed"] == {"charging": 0, "power": 0, "scenario": 0, "scripts": 0, "agent": 0}
    assert result["mqtt_queue_size"] == 0
    task = asyncio.create_task(asyncio.sleep(10), name="charging-test-monitor")
    app.state.charging.tasks["test-monitor"] = task
    try:
        assert runtime_state(app)["managed"]["charging"] == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        app.state.charging.tasks.pop("test-monitor")
    assert runtime_state(app)["managed"]["charging"] == 0
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/test/runtime")).status_code == 404


def test_monitor_refuses_normal_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(RuntimeError, match="APP_ENV=test"):
        create_test_app()
