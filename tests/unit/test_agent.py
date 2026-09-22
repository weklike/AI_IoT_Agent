import json

import httpx
import pytest

from backend.app.agent.provider import RealProvider, validate_message
from backend.app.agent.tools import schemas
from backend.app.config import Settings
from backend.app.errors import DomainError


@pytest.mark.parametrize(
    "status,code",
    [(401, "MODEL_AUTH_ERROR"), (429, "MODEL_RATE_LIMITED"), (500, "MODEL_HTTP_ERROR")],
)
async def test_real_http_errors_without_retry(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "sensitive upstream text"}})

    settings = Settings(
        _env_file=None,
        app_env="test",
        llm_mode="real",
        llm_base_url="https://example.invalid/v1",
        llm_model="test-model",
        llm_api_key="synthetic-sentinel",
    )
    provider = RealProvider(settings, transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(DomainError) as error:
            await provider.complete([{"role": "user", "content": "test"}], schemas(False), 20)
        assert error.value.code == code
        assert "sensitive" not in str(error.value)
        assert len(calls) == 1
    finally:
        await provider.close()


async def test_real_adapter_preserves_assistant_tool_calls_and_pairing():
    observed = []

    def handler(request):
        observed.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "工具结果已收到"}}],
                "usage": {"total_tokens": 17},
            },
        )

    settings = Settings(
        _env_file=None,
        app_env="test",
        llm_mode="real",
        llm_base_url="https://example.invalid/v1",
        llm_model="test-model",
        llm_api_key="synthetic-sentinel",
    )
    provider = RealProvider(settings, transport=httpx.MockTransport(handler))
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "provider-1",
                    "type": "function",
                    "function": {
                        "name": "get_device_status",
                        "arguments": '{"device_id":"CHG-002"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "provider-1", "content": '{"ok":true}'},
    ]
    try:
        await provider.complete(messages, schemas(False), 20)
        assert observed[0]["messages"] == messages
        assert provider.last_usage == {"total_tokens": 17}
        assert all(tool["function"]["name"] != "create_work_order" for tool in observed[0]["tools"])
    finally:
        await provider.close()


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": None},
        {"role": "assistant", "content": "x", "tool_calls": {}},
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "x", "type": "function", "function": {"name": "x", "arguments": {}}}
            ],
        },
    ],
)
def test_protocol_validation(response):
    with pytest.raises(DomainError) as error:
        validate_message(response)
    assert error.value.code == "MODEL_PROTOCOL_ERROR"


def test_schema_cannot_accept_server_context():
    write = next(
        tool["function"]
        for tool in schemas(True)
        if tool["function"]["name"] == "create_work_order"
    )
    assert set(write["parameters"]["properties"]) == {"device_id", "reason_code"}
    assert write["parameters"]["additionalProperties"] is False


def test_valid_final_response_allows_empty_tool_list():
    response = {"role": "assistant", "content": "查询完成", "tool_calls": []}
    assert validate_message(response) == response
