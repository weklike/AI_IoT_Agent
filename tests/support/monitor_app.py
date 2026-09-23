"""Read-only instrumentation for owned test stacks; normal app has no test route."""

import asyncio
import os

from backend.app.config import Settings
from backend.app.main import create_app


def runtime_state(app):
    state = app.state
    tasks = [task for task in asyncio.all_tasks() if not task.done()]
    return {
        "task_count": len(tasks),
        "mqtt_queue_size": state.mqtt.queue.qsize(),
        "guardians": {
            name: sum(task.get_name() == name for task in tasks)
            for name in ("mqtt-consumer", "alarm-timer", "patrol-timer")
        },
        "managed": {
            "charging": sum(not task.done() for task in state.charging.tasks.values()),
            "power": sum(not task.done() for task in state.power.tasks.values()),
            "scenario": sum(not task.done() for task in state.control.tasks),
            "scripts": sum(not task.done() for task in state.scripts.tasks.values()),
            "agent": int(state.scheduler.task is not None and not state.scheduler.task.done()),
        },
    }


def create_test_app():
    if os.getenv("APP_ENV") != "test":
        raise RuntimeError("Runtime instrumentation requires APP_ENV=test")
    settings = Settings()
    if settings.llm_mode != "fixture":
        raise RuntimeError("Stability instrumentation requires fixture mode")
    app = create_app(settings)

    @app.get("/api/test/runtime")
    async def metrics():
        return runtime_state(app)

    return app
