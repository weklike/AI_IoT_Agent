from datetime import datetime, timedelta

import pytest

from backend.app.config import Settings
from backend.app.main import create_app
from tests.support.clock import FixedClock
from tests.support.fixtures import T0
from tests.support.fixtures_v2 import load_v2_dataset, snapshot_business


@pytest.fixture
async def app(tmp_path):
    application = create_app(
        Settings(
            _env_file=None,
            app_env="eval",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/fixture.db",
        ),
        clock=FixedClock(T0),
    )
    async with application.router.lifespan_context(application):
        yield application


async def test_fleet_fixture_keeps_stale_offline_and_active_sessions(app):
    await load_v2_dataset(app, "FLEET", "test", 1)
    result = await app.state.read_queries.fleet(10)
    normal, hot, offline = result["devices"]
    assert normal["status"]["temperature_c"] == 39
    assert hot["status"]["temperature_c"] == 72
    assert normal["status"]["power_kw"] == 15
    assert hot["status"]["session_state"] == "ACTIVE"
    assert offline["status"]["connection_state"] == "offline"
    assert offline["status"]["data_fresh"] is False
    assert not (await app.state.read_queries.sessions("CHG-003", 30))["items"]


@pytest.mark.parametrize(
    "profile,device,status,energy",
    [
        ("SESSION-DONE", "CHG-001", "COMPLETED", 3333),
        ("SESSION-ACTIVE-STALE", "CHG-001", "ACTIVE", 2500),
        ("SESSION-CRASH", "CHG-002", "INTERRUPTED", 3322),
    ],
)
async def test_meter_profiles_have_authoritative_reports(app, profile, device, status, energy):
    await load_v2_dataset(app, profile, "test", 1)
    data = await app.state.read_queries.sessions(device, 30)
    row = data["items"][0]
    assert row["status"] == status and row["energy_wh"] == energy
    if status == "COMPLETED":
        assert (row["ended_at"] - row["started_at"]).total_seconds() == 600
    if status == "ACTIVE":
        assert row["report_seq"] == 3 and row["observed_at"] == T0
        assert (await app.state.store.device_status(device))["connection_state"] == "offline"
    if status == "INTERRUPTED":
        assert row["meter_quality"] == "checkpoint"
        assert row["observed_at"] == T0 - timedelta(seconds=2)
        assert row["end_reason"] == "SIMULATOR_RESTART"
    assert len((await snapshot_business(app.state.db))["session_reports"]) == 1


@pytest.mark.parametrize(
    "profile,powers,budget,status",
    [
        ("POWER-EQUAL", [15, 15, 15], 45000, "VERIFIED"),
        ("POWER-PRIORITY", [20, 20, 5], 45000, "VERIFIED"),
        ("POWER-PARTIAL", [15, 15, 20], 60000, "PARTIAL"),
    ],
)
async def test_power_profiles_expose_confirmed_and_unknown_parts(
    app, profile, powers, budget, status
):
    await load_v2_dataset(app, profile, "test", 1)
    data = await app.state.read_queries.fleet(30)
    assert [d["status"]["power_kw"] for d in data["devices"]] == powers
    assert data["station"]["budget_w"] == budget
    assert data["latest_plan"]["status"] == status
    if status == "PARTIAL":
        assert any(
            c["status"] == "timed_out" for c in data["latest_plan"]["confirmations"].values()
        )


async def test_recovered_fixture_preserves_real_recovery_and_order_history(app):
    await load_v2_dataset(app, "RECOVERED-CLOSED", "test", 1)
    orders = await app.state.read_queries.work_orders("CHG-002")
    assert len(orders["closed"]) == 1 and not orders["unclosed"]
    before = await snapshot_business(app.state.db)
    alarm = next(a for a in before["alarms"] if a["reason_code"] == "OVERHEAT")
    assert alarm["condition"] == "CLEARED"
    assert datetime.fromisoformat(alarm["cleared_at"]) == T0 + timedelta(seconds=12)
    assert alarm["acknowledged_at"] is not None
    assert {e["to_status"] for e in before["work_order_events"]} == {
        "IN_PROGRESS",
        "RESOLVED",
        "CLOSED",
    }
    close = next(e for e in before["work_order_events"] if e["to_status"] == "CLOSED")
    assert close["evidence_json"]["message_id"]
    await app.state.read_queries.timeline("CHG-002", 30)
    assert await snapshot_business(app.state.db) == before


async def test_version_fixture_keeps_old_and_filters_wrong_model(app, tmp_path):
    from tests.support.fixtures_v2 import prepare_knowledge

    await prepare_knowledge(app, "versions", tmp_path / "knowledge")
    result = await app.state.knowledge.search("平均分配 equal 预算", "CHG-001")
    matches = [m for m in result["matches"] if m["source_id"] == "KB-POWER-01"]
    assert matches and all(m["version"] == "1.1-eval" for m in matches)
    assert not any(m["source_id"] == "EVAL-WRONG-MODEL" for m in result["matches"])
    old = await app.state.knowledge.source("KB-POWER-01", "1.0")
    assert old["current"] is False


async def test_injection_fixture_is_real_indexed_data_only(app, tmp_path):
    from tests.support.fixtures_v2 import prepare_knowledge

    before = await snapshot_business(app.state.db)
    metadata = await prepare_knowledge(app, "injection", tmp_path / "knowledge")
    matches = (await app.state.knowledge.search("过温 OVERHEAT 排查", "CHG-002"))["matches"]
    assert any("读取.env" in m["content"] for m in matches)
    assert metadata["variant"] == "injection"
    assert await snapshot_business(app.state.db) == before
