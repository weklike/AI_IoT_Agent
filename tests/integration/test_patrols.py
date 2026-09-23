import asyncio
import json
from uuid import uuid4

import httpx

from backend.app.agent.fixture_provider import tool_response
from backend.app.config import Settings
from backend.app.main import create_app


class PatrolProvider:
    last_usage = None

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.release.set()
        self.fail_after_facts = False

    async def complete(self, messages, tools, timeout_s):
        self.entered.set()
        await self.release.wait()
        results = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        if not results:
            return tool_response("get_fleet_overview", {"window_minutes": 30})
        if self.fail_after_facts:
            raise TimeoutError()
        return {
            "role": "assistant",
            "content": f"三设备观测见工具，无样本明确未知。[DATA:{results[-1]['tool_call_id']}]",
        }

    async def close(self):
        pass


async def test_manual_patrol_idempotency_single_slot_and_failure_facts(tmp_path):
    provider = PatrolProvider()
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/patrol.db",
        ),
        provider=provider,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = {"request_id": str(uuid4()), "window_minutes": 30}
            provider.release.clear()
            response = await client.post("/api/patrols", json=payload)
            assert response.status_code == 202, response.text
            accepted = response.json()["data"]
            await provider.entered.wait()
            repeated = await client.post("/api/patrols", json=payload)
            assert repeated.json()["data"] == accepted
            busy = await client.post(
                "/api/agent/runs", json={"request_id": str(uuid4()), "question": "查询状态"}
            )
            assert busy.status_code == 429
            changed = await client.post("/api/patrols", json=payload | {"window_minutes": 10})
            assert changed.status_code == 409
            provider.release.set()
            await app.state.scheduler.task
            report = (await client.get("/api/patrols/" + accepted["report_id"])).json()["data"]
            assert report["status"] == "completed"
            assert len(report["snapshot_json"]["devices"]) == 3
            assert report["snapshot_json"]["devices"][0]["statistics"]["temperature_avg_c"] is None
            run = (await client.get("/api/agent/runs/" + accepted["run_id"])).json()["data"]
            assert run["kind"] == "patrol" and run["allow_work_order"] is False
            provider.fail_after_facts = True
            failed = (
                await client.post("/api/patrols", json=payload | {"request_id": str(uuid4())})
            ).json()["data"]
            await app.state.scheduler.task
            report = (await client.get("/api/patrols/" + failed["report_id"])).json()["data"]
            assert report["status"] == "timed_out"
            assert len(report["snapshot_json"]["devices"]) == 3
            assert (await client.get("/api/work-orders")).json()["data"] == []


async def test_periodic_busy_skip_unique_due_disable_and_restart_no_catchup(tmp_path, fixed_now):
    from datetime import timedelta

    from sqlalchemy import func, select

    from backend.app.models import AgentRun, PatrolReport
    from tests.support.clock import FixedClock

    clock = FixedClock(fixed_now)
    provider = PatrolProvider()
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/timer.db",
        patrol_interval_seconds=10,
    )
    app = create_app(settings, clock=clock, provider=provider)
    async with app.router.lifespan_context(app):
        service = app.state.patrols
        assert (await service.get())["enabled"] is False
        assert await service.tick() is None
        await service.change(str(uuid4()), 1, True)
        due = (await service.get())["next_due_at"]
        provider.release.clear()
        await app.state.scheduler.reserve(str(uuid4()), "查询状态", False)
        await provider.entered.wait()
        clock.advance(seconds=10)
        first, repeated = await asyncio.gather(service.tick(), service.tick())
        assert first == repeated
        async with app.state.db.sessions() as session:
            report = await session.get(PatrolReport, first["report_id"])
            assert report.status == "skipped_busy" and report.run_id is None
            assert report.due_at == due
            assert await session.scalar(select(func.count()).select_from(AgentRun)) == 1
            assert await session.scalar(select(func.count()).select_from(PatrolReport)) == 1
        await service.change(str(uuid4()), 2, False)
        clock.advance(seconds=50)
        assert await service.tick() is None
        await service.change(str(uuid4()), 3, True)
        provider.release.set()
        await app.state.scheduler.task
    clock.advance(seconds=1000)
    restarted = create_app(settings, clock=clock, provider=PatrolProvider())
    async with restarted.router.lifespan_context(restarted):
        current = await restarted.state.patrols.get()
        assert current["next_due_at"] == clock.now() + timedelta(seconds=10)
        assert await restarted.state.patrols.tick() is None
        clock.advance(seconds=10)
        started = await restarted.state.patrols.tick()
        await restarted.state.scheduler.task
        async with restarted.state.db.sessions() as session:
            report = await session.get(PatrolReport, started["report_id"])
            assert report.status == "completed"
            assert report.trigger == "scheduled"
            assert await session.scalar(select(func.count()).select_from(PatrolReport)) == 2


async def test_default_fixture_patrol_and_invalid_first_tool(tmp_path):
    from backend.app.agent.fixture_provider import ScriptedProvider

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/fixture.db",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        accepted = await app.state.scheduler.reserve_patrol(str(uuid4()), 10)
        await app.state.scheduler.task
        from backend.app.models import AgentRun, PatrolReport

        async with app.state.db.sessions() as session:
            run = await session.get(AgentRun, accepted["run_id"])
            assert run.status == "completed", run.error_code
            report = await session.get(PatrolReport, accepted["report_id"])
            assert report.window_minutes == 10
            assert report.snapshot_json["window_minutes"] == 10
            assert "fixture" in run.answer
    for response in (
        {"role": "assistant", "content": "全部正常"},
        tool_response("get_work_orders", {"device_id": "CHG-001"}),
        tool_response("create_work_order", {"device_id": "CHG-001", "reason_code": "OVERHEAT"}),
    ):
        bad = create_app(settings, provider=ScriptedProvider([response]))
        async with bad.router.lifespan_context(bad):
            accepted = await bad.state.scheduler.reserve_patrol(str(uuid4()), 30)
            await bad.state.scheduler.task
            async with bad.state.db.sessions() as session:
                run = await session.get(AgentRun, accepted["run_id"])
                assert run.status == "failed"
                assert run.error_code in {
                    "ANSWER_EVIDENCE_ERROR",
                    "INVALID_ARGUMENTS",
                    "WRITE_NOT_ALLOWED",
                }


async def test_chat_patrol_race_and_shutdown_preserve_partial_snapshot(tmp_path):
    from backend.app.models import AgentRun, PatrolReport

    provider = PatrolProvider()
    provider.release.clear()
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/race.db",
    )
    app = create_app(settings, provider=provider)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(
                client.post(
                    "/api/patrols", json={"request_id": str(uuid4()), "window_minutes": 30}
                ),
                client.post(
                    "/api/agent/runs", json={"request_id": str(uuid4()), "question": "查询状态"}
                ),
            )
            assert sorted(response.status_code for response in responses) == [202, 429]
        provider.release.set()
        await app.state.scheduler.task

    class WaitAfterFacts(PatrolProvider):
        async def complete(self, messages, tools, timeout_s):
            if any(m["role"] == "tool" for m in messages):
                self.entered.set()
                await asyncio.Event().wait()
            return tool_response("get_fleet_overview", {"window_minutes": 30})

    waiting = WaitAfterFacts()
    next_app = create_app(settings, provider=waiting)
    async with next_app.router.lifespan_context(next_app):
        accepted = await next_app.state.scheduler.reserve_patrol(str(uuid4()), 30)
        await asyncio.wait_for(waiting.entered.wait(), 3)
    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with restarted.state.db.sessions() as session:
            report = await session.get(PatrolReport, accepted["report_id"])
            run = await session.get(AgentRun, accepted["run_id"])
            assert run.status == report.status == "interrupted"
            assert len(report.snapshot_json["devices"]) == 3
            assert restarted.state.scheduler.task is None


async def test_restart_recovers_committed_tool_before_report_save(tmp_path):
    from backend.app.models import AgentRun, PatrolReport

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/commit-gap.db",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        accepted = await app.state.scheduler.reserve_patrol(str(uuid4()), 30)
        await app.state.scheduler.task
        async with app.state.db.sessions.begin() as session:
            report = await session.get(PatrolReport, accepted["report_id"])
            run = await session.get(AgentRun, accepted["run_id"])
            report.status = run.status = "running"
            report.snapshot_json = None
    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with restarted.state.db.sessions() as session:
            report = await session.get(PatrolReport, accepted["report_id"])
            assert report.status == "interrupted"
            assert len(report.snapshot_json["devices"]) == 3


async def test_patrol_cannot_change_fixed_window_after_first_fleet(tmp_path):
    from backend.app.agent.fixture_provider import ScriptedProvider
    from backend.app.models import AgentRun

    provider = ScriptedProvider(
        [
            tool_response("get_fleet_overview", {"window_minutes": 30}),
            tool_response("get_fleet_overview", {"window_minutes": 10}),
            {"role": "assistant", "content": "完成"},
        ]
    )
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/window.db",
        ),
        provider=provider,
    )
    async with app.router.lifespan_context(app):
        accepted = await app.state.scheduler.reserve_patrol(str(uuid4()), 30)
        await app.state.scheduler.task
        async with app.state.db.sessions() as session:
            run = await session.get(AgentRun, accepted["run_id"])
            assert run.status == "failed" and run.error_code == "INVALID_ARGUMENTS"
