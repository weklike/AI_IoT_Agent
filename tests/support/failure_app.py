"""Controlled E2E failures; only launched by the test Compose override."""

import asyncio
import os

from backend.app.agent.fixture_provider import FixtureProvider, tool_response
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AgentRun


class FailureProvider(FixtureProvider):
    async def complete(self, messages, tools, timeout_s):
        question = next(message["content"] for message in messages if message["role"] == "user")
        if question == "测试模型超时":
            await asyncio.sleep(21)
        if question == "测试工具超时":
            return tool_response(
                "get_device_history", {"device_id": "CHG-002", "window_minutes": 10}
            )
        return await super().complete(messages, tools, timeout_s)


def create_test_app():
    if os.getenv("APP_ENV") != "test":
        raise RuntimeError("Test app requires APP_ENV=test")
    settings = Settings()
    if settings.llm_mode != "fixture":
        raise RuntimeError("Test failures never enter real mode")
    app = create_app(settings, provider=FailureProvider())
    original = app.state.runner.executor.invoke

    async def invoke(name, args, context):
        if name == "get_device_history":
            async with app.state.db.sessions() as session:
                run = await session.get(AgentRun, str(context.run_id))
                should_delay = run.question == "测试工具超时"
            if should_delay:
                await asyncio.sleep(4)
        return await original(name, args, context)

    app.state.runner.executor.invoke = invoke
    return app
