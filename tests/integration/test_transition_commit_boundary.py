from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import OperationRequest, WorkOrder, WorkOrderEvent
from backend.app.work_orders import WorkOrderService
from tests.support.clock import FixedClock
from tests.support.fixtures_v2 import load_v2_dataset


async def test_lost_transition_commit_response_recovers_only_the_same_request(
    tmp_path, fixed_now, monkeypatch
):
    clock = FixedClock(fixed_now)
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/commit.db",
        ),
        clock=clock,
    )
    async with app.router.lifespan_context(app):
        await load_v2_dataset(app, "HOT-IN_PROGRESS", "transition-commit", 1)
        async with app.state.db.sessions() as session:
            order = await session.scalar(select(WorkOrder))
            identity, version = order.order_id, order.version
        orders = WorkOrderService(app.state.db, app.state.settings, clock)
        request_id = str(uuid4())
        commit = AsyncSession.commit
        lost = False

        async def commit_then_lose_response(session):
            nonlocal lost
            await commit(session)
            if not lost:
                lost = True
                raise ConnectionError("injected lost response after durable commit")

        monkeypatch.setattr(AsyncSession, "commit", commit_then_lose_response)
        with pytest.raises(ConnectionError, match="durable commit"):
            await orders.transition(identity, request_id, version, "RESOLVED", "已处理，等待恢复")
        recovered = await orders.transition(
            identity, request_id, version, "RESOLVED", "已处理，等待恢复"
        )
        assert recovered["status"] == "RESOLVED" and recovered["version"] == version + 1
        async with app.state.db.sessions() as session:
            saved = await session.get(OperationRequest, request_id)
            assert saved.result_json == recovered
            assert (await session.get(WorkOrder, identity)).version == version + 1
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(WorkOrderEvent)
                    .where(
                        WorkOrderEvent.order_id == identity, WorkOrderEvent.to_status == "RESOLVED"
                    )
                )
                == 1
            )
