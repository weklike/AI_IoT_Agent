import httpx
import pytest
from sqlalchemy import text

from backend.app.config import Settings
from backend.app.db import Database
from backend.app.main import create_app


async def test_database_pragmas_seeds_and_restart(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
    )
    db = Database(settings)
    await db.initialize()
    async with db.sessions() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1
        assert (await session.execute(text("PRAGMA busy_timeout"))).scalar() == 1000
        assert (await session.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
        assert (await session.execute(text("SELECT count(*) FROM devices"))).scalar() == 3
        assert (
            len(
                (
                    await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                ).all()
            )
            == 7
        )
    await db.initialize()
    async with db.sessions() as session:
        assert (await session.execute(text("SELECT count(*) FROM devices"))).scalar() == 3
    await db.close()


async def test_disabled_mqtt_health_explicit(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/test.db",
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")
            assert response.status_code == 200
            assert response.json()["data"]["mqtt"] == "disabled"
            assert response.json()["data"]["llm_mode"] == "fixture"
            assert response.json()["request_id"]


def test_mqtt_cannot_be_disabled_in_local():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="local", mqtt_enabled=False)


def test_missing_real_configuration_explicit():
    with pytest.raises(ValueError, match="LLM_CONFIGURATION_ERROR"):
        Settings(_env_file=None, llm_mode="real", llm_base_url="", llm_model="", llm_api_key="")


def test_real_configuration_error_never_prints_supplied_key():
    with pytest.raises(ValueError) as error:
        Settings(
            _env_file=None,
            llm_mode="real",
            llm_base_url="",
            llm_model="",
            llm_api_key="SYNTHETIC_KEY_SENTINEL",
        )
    assert "SYNTHETIC_KEY_SENTINEL" not in str(error.value)
