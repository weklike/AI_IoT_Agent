"""Write requests serialize locally in SQLite; check replay before business guards."""

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.errors import DomainError
from backend.app.models import OperationRequest


async def execute_operation(
    session: AsyncSession,
    *,
    request_id: str,
    route: str,
    action: str,
    parameters: dict[str, Any],
    now: datetime,
    perform: Callable[[AsyncSession], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Own a short transaction. The callback must not publish or wait on network IO."""
    digest = hashlib.sha256(
        json.dumps(
            [route, action, parameters],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    if session.in_transaction():
        raise RuntimeError("Operation requires an independent session")
    try:
        await session.execute(text("BEGIN IMMEDIATE"))
        previous = await session.get(OperationRequest, request_id)
        if previous is not None:
            if previous.request_hash != digest:
                raise DomainError("REQUEST_CONFLICT", "请求 ID 已用于不同操作", 409)
            result = previous.result_json
        else:
            operation = OperationRequest(
                request_id=request_id,
                request_hash=digest,
                route=route,
                action=action,
                result_json={},
                created_at=now,
            )
            session.add(operation)
            await session.flush()
            result = await perform(session)
            operation.result_json = result
        await session.commit()
        return result
    except OperationalError as error:
        await session.rollback()
        raise DomainError("DATABASE_UNAVAILABLE", "数据库写入不可用", 503) from error
    except BaseException:
        await session.rollback()
        raise
