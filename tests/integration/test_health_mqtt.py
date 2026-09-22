import asyncio

import httpx

from backend.app.config import Settings
from backend.app.main import create_app
from tests.support.resources import broker, free_port


async def test_real_mqtt_health_and_shutdown(tmp_path):
    with broker() as (port, prefix):
        settings = Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=port,
            mqtt_topic_prefix=prefix,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/db.sqlite",
        )
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                async with asyncio.timeout(10):
                    while not app.state.mqtt.connected:
                        await asyncio.sleep(0.05)
                response = await client.get("/api/health")
                assert response.status_code == 200
                assert response.json()["data"]["mqtt"] == "ready"
        assert not app.state.mqtt.connected


async def test_missing_broker_is_503(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_port=free_port(),
            database_url=f"sqlite+aiosqlite:///{tmp_path}/db.sqlite",
        )
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")
            assert response.status_code == 503
            assert response.json()["data"]["mqtt"] == "unavailable"
