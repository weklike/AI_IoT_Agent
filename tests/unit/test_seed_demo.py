from backend.app.config import Settings
from backend.app.db import Database
from backend.app.models import Device
from scripts.seed_demo import initialize_empty


async def test_seed_never_clears_existing_live_state(tmp_path, fixed_now):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/demo.db",
    )
    assert await initialize_empty(settings) == "created"
    db = Database(settings)
    async with db.sessions.begin() as session:
        device = await session.get(Device, "CHG-001")
        device.last_live_received_at = fixed_now
    await db.close()
    assert await initialize_empty(settings) == "already_initialized"
    db = Database(settings)
    try:
        async with db.sessions() as session:
            assert (await session.get(Device, "CHG-001")).last_live_received_at == fixed_now
    finally:
        await db.close()
