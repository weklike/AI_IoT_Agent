import pytest
from sqlalchemy import select

from backend.app.contracts import TelemetryV2
from backend.app.models import Telemetry
from tests.integration.test_eval_v2_fixtures import app as app
from tests.support.fixtures import T0
from tests.support.query_dataset_v2 import seed


async def test_performance_dataset_sizes_and_telemetry_contract(app):
    result = await seed(app.state.db, T0)
    assert result["counts"] == {
        "telemetry": 5403,
        "charging_sessions": 90,
        "alarm_events": 60,
        "work_order_events": 60,
        "knowledge_documents": 24,
    }
    async with app.state.db.sessions() as session:
        for row in (
            await session.scalars(select(Telemetry).where(Telemetry.device_id == "CHG-001"))
        ).all():
            data = {
                c.name: getattr(row, c.name)
                for c in Telemetry.__table__.columns
                if c.name not in {"id", "received_at"}
            }
            TelemetryV2.model_validate(data)
    with pytest.raises(RuntimeError, match="nonempty"):
        await seed(app.state.db, T0)
