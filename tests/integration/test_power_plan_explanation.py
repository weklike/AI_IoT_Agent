from uuid import uuid4

from sqlalchemy import select

from backend.app.models import PowerPlan
from tests.integration.test_eval_v2_fixtures import app as app
from tests.support.fixtures_v2 import load_v2_dataset


async def test_saved_priority_order_is_exposed_as_actual_fleet_evidence(app):
    await load_v2_dataset(app, "POWER-PRIORITY", "explanation", 1)
    order = ["CHG-003", "CHG-002", "CHG-001"]
    accepted = await app.state.power.preview(str(uuid4()), 45000, "priority", order)
    saved = await app.state.power.get(accepted["plan_id"])
    assert saved["snapshot_json"]["device_priority"] == order
    latest = (await app.state.read_queries.fleet(30))["latest_plan"]
    assert latest["strategy"] == "priority"
    assert latest["device_priority"] == order
    assert latest["allocation_json"] == {"CHG-001": 5000, "CHG-002": 20000, "CHG-003": 20000}


async def test_legacy_plan_does_not_invent_an_unrecorded_priority(app):
    await load_v2_dataset(app, "POWER-PRIORITY", "legacy-explanation", 1)
    async with app.state.db.sessions.begin() as session:
        plan = await session.scalar(select(PowerPlan))
        plan.snapshot_json = {"confirmed_budget_w": 60000, "fixture": True}
    latest = (await app.state.read_queries.fleet(30))["latest_plan"]
    assert latest["strategy"] == "priority"
    assert latest["device_priority"] is None
