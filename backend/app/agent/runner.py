import asyncio
import json
import logging
import time
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from backend.app.agent.prompts import SYSTEM_PROMPT
from backend.app.agent.provider import Provider, validate_message
from backend.app.agent.tools import ToolExecutor, schemas, validate_call
from backend.app.api import json_data
from backend.app.clocks import DataClock
from backend.app.config import Settings
from backend.app.contracts import ToolContext
from backend.app.db import Database
from backend.app.errors import DomainError
from backend.app.models import AgentRun, ToolCall
from backend.app.telemetry.ingest import TelemetryStore

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        clock: DataClock,
        provider: Provider,
        store: TelemetryStore,
    ):
        self.db, self.settings, self.clock, self.provider = db, settings, clock, provider
        self.executor = ToolExecutor(db, settings, clock, store)

    async def _save(self, run_id: str, **fields):
        async with self.db.sessions.begin() as session:
            row = await session.get(AgentRun, run_id)
            for key, value in fields.items():
                setattr(row, key, value)

    async def _interrupted_tool(
        self, task: asyncio.Task, context: ToolContext, code: str, writing: bool
    ):
        task.cancel()
        # SQLAlchemy session ownership stays inside the tool. Wait for commit/rollback before querying.
        try:
            async with asyncio.timeout(self.settings.agent_cleanup_timeout_seconds):
                await asyncio.gather(task, return_exceptions=True)
                async with self.db.sessions.begin() as session:
                    row = await session.get(ToolCall, str(context.tool_call_id))
                    if row and row.result_json and row.result_json.get("ok") and writing:
                        return row.result_json
                    if row:
                        row.status, row.error_code = "failed", code
                        row.result_json = {
                            "tool_call_id": row.tool_call_id,
                            "ok": False,
                            "data": None,
                            "error": {"code": code, "message": "工具执行中断"},
                        }
        except (TimeoutError, SQLAlchemyError) as exc:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            raise DomainError(
                "WRITE_RESULT_UNKNOWN" if writing else code,
                "执行结果未确认，请查看记录；不要盲目重试",
            ) from exc
        return None

    async def run(self, run_id: str):
        messages: list[dict] = []
        metrics: list[dict] = []
        deadline = time.monotonic() + self.settings.agent_total_timeout_seconds
        status, error, answer = "failed", None, None
        try:
            async with self.db.sessions() as session:
                row = await session.get(AgentRun, run_id)
                allowed, question = row.allow_work_order, row.question
            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT + "\n当前数据时钟：" + self.clock.now().isoformat(),
                },
                {"role": "user", "content": question},
            ]
            await self._save(run_id, status="running", messages_json=messages)
            count = 0
            seen: set[str] = set()
            for _ in range(self.settings.agent_max_model_requests):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DomainError("AGENT_TIMEOUT", "整轮执行超时")
                started = time.monotonic()
                try:
                    async with asyncio.timeout(
                        min(self.settings.agent_model_timeout_seconds, remaining)
                    ):
                        response = await self.provider.complete(
                            messages,
                            schemas(allowed),
                            min(self.settings.agent_model_timeout_seconds, remaining),
                        )
                except TimeoutError as exc:
                    code = "AGENT_TIMEOUT" if time.monotonic() >= deadline else "MODEL_TIMEOUT"
                    raise DomainError(code, "模型请求超时") from exc
                finally:
                    metrics.append(
                        {
                            "duration_ms": (time.monotonic() - started) * 1000,
                            "usage": getattr(self.provider, "last_usage", None),
                        }
                    )
                if time.monotonic() >= deadline:
                    raise DomainError("AGENT_TIMEOUT", "整轮执行超时")
                response = validate_message(response)
                messages.append(response)
                await self._save(
                    run_id, messages_json=json_data(messages), model_metrics_json=metrics
                )
                if time.monotonic() >= deadline:
                    raise DomainError("AGENT_TIMEOUT", "整轮执行超时")
                calls = response.get("tool_calls") or []
                if not calls:
                    answer, status = response["content"], "completed"
                    break
                if any(call["id"] in seen for call in calls) or len(
                    {call["id"] for call in calls}
                ) != len(calls):
                    raise DomainError("MODEL_PROTOCOL_ERROR", "工具协议 ID 重复")
                seen.update(call["id"] for call in calls)
                if count + len(calls) > self.settings.agent_max_tool_calls:
                    raise DomainError("BUDGET_EXCEEDED", "工具调用预算已耗尽")
                parsed = []
                for candidate in calls:
                    try:
                        parsed.append(validate_call(candidate, allowed))
                    except DomainError as rejected:
                        identifier = str(uuid4())
                        try:
                            rejected_args = json.loads(candidate["function"]["arguments"])
                        except ValueError:
                            rejected_args = {
                                "unparsed_arguments": candidate["function"]["arguments"]
                            }
                        result = {
                            "tool_call_id": identifier,
                            "ok": False,
                            "data": None,
                            "error": {"code": rejected.code, "message": rejected.message},
                        }
                        async with self.db.sessions.begin() as session:
                            session.add(
                                ToolCall(
                                    tool_call_id=identifier,
                                    provider_call_id=candidate["id"],
                                    ordinal=count + 1,
                                    run_id=run_id,
                                    tool_name=candidate["function"]["name"],
                                    args_json=rejected_args,
                                    result_json=result,
                                    status="failed",
                                    started_at=self.clock.now(),
                                    duration_ms=0,
                                    error_code=rejected.code,
                                )
                            )
                        raise
                for call, args in zip(calls, parsed):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise DomainError("AGENT_TIMEOUT", "整轮执行超时")
                    context = ToolContext(
                        run_id=run_id, tool_call_id=uuid4(), allow_work_order=allowed
                    )
                    task = asyncio.create_task(
                        self.executor.execute(call, args, context, ordinal=count + 1),
                        name=f"tool-{context.tool_call_id}",
                    )
                    count += 1
                    writing = call["function"]["name"] == "create_work_order"
                    try:
                        async with asyncio.timeout(
                            min(self.settings.agent_tool_timeout_seconds, remaining)
                        ):
                            result = await asyncio.shield(task)
                    except (TimeoutError, asyncio.CancelledError) as exc:
                        code = (
                            "PROCESS_INTERRUPTED"
                            if isinstance(exc, asyncio.CancelledError)
                            else "AGENT_TIMEOUT"
                            if time.monotonic() >= deadline
                            else "TOOL_TIMEOUT"
                        )
                        restored = await self._interrupted_tool(task, context, code, writing)
                        if restored:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": call["id"],
                                    "content": json.dumps(restored, ensure_ascii=False),
                                }
                            )
                        if isinstance(exc, asyncio.CancelledError):
                            raise
                        raise DomainError(code, "工具执行超时；已停止后续调度") from exc
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    await self._save(run_id, messages_json=json_data(messages))
                    if not result["ok"]:
                        raise DomainError(result["error"]["code"], result["error"]["message"])
            else:
                raise DomainError("BUDGET_EXCEEDED", "模型请求预算已耗尽")
        except DomainError as exc:
            error = exc.code
            status = (
                "timed_out"
                if exc.code in {"AGENT_TIMEOUT", "MODEL_TIMEOUT", "TOOL_TIMEOUT"}
                else "failed"
            )
            answer = exc.message
        except asyncio.CancelledError:
            status, error, answer = "interrupted", "PROCESS_INTERRUPTED", "服务关闭，任务已中断"
        except SQLAlchemyError:
            status, error, answer = "failed", "DATABASE_UNAVAILABLE", "数据库暂不可用，任务未完成"
            logger.error("AGENT_DATABASE_ERROR run_id=%s", run_id)
        except Exception:
            status, error, answer = "failed", "INTERNAL_ERROR", "任务执行失败，请查看关联日志"
            logger.exception("AGENT_INTERNAL_ERROR run_id=%s", run_id)
        finally:
            await self._save(
                run_id,
                status=status,
                error_code=error,
                answer=answer,
                finished_at=self.clock.now(),
                messages_json=json_data(messages),
                model_metrics_json=metrics,
            )
