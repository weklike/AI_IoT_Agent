from typing import Protocol

import httpx

from backend.app.config import Settings
from backend.app.errors import DomainError


class Provider(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict], timeout_s: float) -> dict: ...
    async def close(self) -> None: ...


def validate_message(message: dict) -> dict:
    if not isinstance(message, dict) or message.get("role") != "assistant":
        raise DomainError("MODEL_PROTOCOL_ERROR", "模型响应结构无效")
    calls = message.get("tool_calls")
    content = message.get("content")
    if content is not None and not isinstance(content, str):
        raise DomainError("MODEL_PROTOCOL_ERROR", "模型正文类型无效")
    if calls is not None and (not isinstance(calls, list) or not calls):
        raise DomainError("MODEL_PROTOCOL_ERROR", "模型工具调用结构无效")
    if calls:
        for call in calls:
            if (
                not isinstance(call, dict)
                or not isinstance(call.get("id"), str)
                or not call["id"]
                or call.get("type") != "function"
            ):
                raise DomainError("MODEL_PROTOCOL_ERROR", "模型工具调用标识无效")
            function = call.get("function")
            if (
                not isinstance(function, dict)
                or not isinstance(function.get("name"), str)
                or not isinstance(function.get("arguments"), str)
            ):
                raise DomainError("MODEL_PROTOCOL_ERROR", "模型函数结构无效")
    elif not content or not content.strip():
        raise DomainError("MODEL_PROTOCOL_ERROR", "模型最终回答为空")
    return message


class RealProvider:
    """One Chat Completions protocol adapter; endpoint compatibility needs a real smoke test."""

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.client = httpx.AsyncClient(transport=transport, follow_redirects=False)
        self.last_usage: dict | None = None

    async def complete(self, messages: list[dict], tools: list[dict], timeout_s: float) -> dict:
        self.last_usage = None
        try:
            response = await self.client.post(
                self.settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + self.settings.llm_api_key.get_secret_value()},
                json={"model": self.settings.llm_model, "messages": messages, "tools": tools},
                timeout=timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise DomainError("MODEL_TIMEOUT", "模型请求超时") from exc
        except httpx.HTTPError as exc:
            raise DomainError("MODEL_UNAVAILABLE", "模型网络请求失败") from exc
        if response.status_code != 200:
            code = {401: "MODEL_AUTH_ERROR", 429: "MODEL_RATE_LIMITED"}.get(
                response.status_code, "MODEL_HTTP_ERROR"
            )
            raise DomainError(code, f"模型 HTTP 请求失败（{response.status_code}）")
        try:
            data = response.json()
            message = data["choices"][0]["message"]
            self.last_usage = data.get("usage")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise DomainError("MODEL_PROTOCOL_ERROR", "模型响应结构无效") from exc
        return validate_message(message)

    async def close(self):
        await self.client.aclose()
