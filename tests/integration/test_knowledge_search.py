import httpx
from sqlalchemy import func, select, text

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import KnowledgeDocument


async def test_cold_start_indexes_sources_and_serves_safe_bounded_search(tmp_path):
    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/knowledge.db",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/knowledge/search", params={"query": "平均分配 equal", "device_id": "CHG-001"}
            )
            assert response.status_code == 200, response.text
            matches = response.json()["data"]["matches"]
            assert any(row["source_id"] == "KB-POWER-01" for row in matches)
            assert len(matches) <= 5 and sum(len(row["content"]) for row in matches) <= 3000
            source = matches[0]
            detail = await client.get(
                f"/api/knowledge/sources/{source['source_id']}/versions/{source['version']}"
            )
            assert detail.status_code == 200
            assert any(
                chunk["chunk_id"] == source["chunk_id"] for chunk in detail.json()["data"]["chunks"]
            )
            for query in ('" OR 1=1 --', "NEAR(foo)", "温"):
                assert (
                    await client.get("/api/knowledge/search", params={"query": query})
                ).status_code == 200
            assert (
                await client.get("/api/knowledge/search", params={"query": " "})
            ).status_code == 422
            health = (await client.get("/api/health")).json()["data"]
            assert health["knowledge"] == "ready"
        async with app.state.db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(KnowledgeDocument)
                    .where(KnowledgeDocument.current)
                )
                == 24
            )
            first = (
                await session.execute(
                    text("SELECT rowid,title,tags,body FROM knowledge_fts ORDER BY rowid")
                )
            ).all()
    restarted = create_app(settings)
    async with restarted.router.lifespan_context(restarted):
        async with restarted.state.db.sessions() as session:
            assert (
                await session.execute(
                    text("SELECT rowid,title,tags,body FROM knowledge_fts ORDER BY rowid")
                )
            ).all() == first


async def test_body_only_incidental_word_does_not_answer_unrelated_subject(tmp_path):
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/noise.db",
        )
    )
    async with app.router.lifespan_context(app):
        matches = (await app.state.knowledge.search("银河望远镜数值", "CHG-001"))["matches"]
        assert matches == []


async def test_rebuild_failure_retains_old_version_and_wrong_model_is_filtered(tmp_path):
    import shutil
    import sqlite3
    from pathlib import Path

    import pytest
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    settings = Settings(
        _env_file=None,
        app_env="test",
        mqtt_enabled=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/rollback-index.db",
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        before = await app.state.knowledge.source("KB-POWER-01", "1.0")
        directory = tmp_path / "corpus"
        shutil.copytree(Path("knowledge"), directory)
        path = directory / "kb-power-01.md"
        path.write_text(
            path.read_text().replace("version: 1.0", "version: 1.1")
            + "\n新增版本说明：仍为模拟预算分配。\n"
        )
        wrong = (
            (directory / "kb-power-02.md")
            .read_text()
            .replace("source_id: KB-POWER-02", "source_id: KB-WRONG-MODEL")
            .replace("applicable_model: SIM-CHG-V2", "applicable_model: REAL-VENDOR-X")
        )
        (directory / "wrong-model.md").write_text(wrong)
        app.state.knowledge_index.directory = directory

        def fail(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith("INSERT INTO knowledge_fts"):
                raise OperationalError(
                    statement, None, sqlite3.OperationalError("injected index failure")
                )

        event.listen(app.state.db.engine.sync_engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(OperationalError):
                await app.state.knowledge_index.refresh()
        finally:
            event.remove(app.state.db.engine.sync_engine, "before_cursor_execute", fail)
        assert not app.state.knowledge_index.available
        assert await app.state.knowledge.source("KB-POWER-01", "1.0") == before
        async with app.state.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(KnowledgeDocument)) == 24
        assert await app.state.knowledge_index.refresh()
        assert not (await app.state.knowledge.source("KB-POWER-01", "1.0"))["current"]
        matches = (await app.state.knowledge.search("平均分配 equal", "CHG-001"))["matches"]
        assert any(row["source_id"] == "KB-POWER-01" and row["version"] == "1.1" for row in matches)
        assert all(
            row["source_id"] != "KB-WRONG-MODEL"
            for row in (await app.state.knowledge.search("优先级 priority", "CHG-001"))["matches"]
        )
        assert all(row["source_id"] != "KB-POWER-01" or row["version"] == "1.1" for row in matches)


async def test_missing_fts_module_exposes_failed_health_without_partial_schema(tmp_path):
    import sqlite3

    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{tmp_path}/no-fts.db",
        )
    )

    def unavailable(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("CREATE VIRTUAL TABLE knowledge_fts"):
            raise OperationalError(
                statement, None, sqlite3.OperationalError("no such module: fts5")
            )

    event.listen(app.state.db.engine.sync_engine, "before_cursor_execute", unavailable)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                health = await client.get("/api/health")
                assert health.status_code == 503
                assert health.json()["data"]["knowledge"] == "unavailable"
                assert health.json()["data"]["db"] == "unavailable"
                assert (await client.get("/api/devices")).status_code == 503
            async with app.state.db.sessions() as session:
                assert (
                    await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                ).all() == []
    finally:
        event.remove(app.state.db.engine.sync_engine, "before_cursor_execute", unavailable)
