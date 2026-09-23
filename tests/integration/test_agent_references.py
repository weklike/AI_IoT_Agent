import json
from uuid import uuid4

import httpx

from backend.app.agent.fixture_provider import tool_response
from backend.app.config import Settings
from backend.app.main import create_app


class ReferenceProvider:
    last_usage = None

    def __init__(self):
        self.foreign = None

    async def complete(self, messages, tools, timeout_s):
        results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        if not results:
            return tool_response(
                "search_fault_knowledge", {"query": "平均分配 equal", "device_id": "CHG-001"}
            )
        result = results[-1]
        match = result["data"]["matches"][0]
        data_id = self.foreign or result["tool_call_id"]
        return {
            "role": "assistant",
            "content": f"检索依据 [KB:{match['source_id']}@{match['version']}#{match['chunk_id']}] [DATA:{data_id}]",
        }

    async def close(self):
        pass


async def test_real_search_refs_persist_and_previous_run_evidence_is_rejected(tmp_path):
    provider = ReferenceProvider()
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/refs.db",
        ),
        provider=provider,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def run():
                response = await client.post(
                    "/api/agent/runs",
                    json={"request_id": str(uuid4()), "question": "平均分配的规则是什么？"},
                )
                assert response.status_code == 202
                await app.state.scheduler.task
                return (
                    await client.get("/api/agent/runs/" + response.json()["data"]["run_id"])
                ).json()["data"]

            first = await run()
            assert first["status"] == "completed", first
            assert len(first["answer_refs"]) == 2
            assert first["answer_refs"][0]["tool_call_id"] == first["tool_calls"][0]["tool_call_id"]
            provider.foreign = first["tool_calls"][0]["tool_call_id"]
            second = await run()
            assert second["status"] == "failed"
            assert second["error_code"] == "ANSWER_EVIDENCE_ERROR"
            assert second["answer_refs"] == []
            assert "[KB:" not in second["answer"]
