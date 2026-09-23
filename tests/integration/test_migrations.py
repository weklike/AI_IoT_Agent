"""Migration tests use frozen v1 SQL, never the evolving ORM to create old databases."""

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.config import Settings
from backend.app.db import Database

V1 = Path(__file__).parents[1] / "fixtures/v1_schema.sql"


def database(path):
    return Database(
        Settings(
            _env_file=None,
            app_env="test",
            mqtt_enabled=False,
            database_url=f"sqlite+aiosqlite:///{path}",
        )
    )


async def test_empty_database_has_versioned_schema(tmp_path):
    db = database(tmp_path / "empty.db")
    try:
        await db.initialize()
        async with db.sessions() as session:
            names = set(
                (
                    await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                ).scalars()
            )
            assert "schema_migrations" in names
            assert "operation_requests" in names
            assert "knowledge_fts" in names
    finally:
        await db.close()


async def test_upgrade_preserves_v1_business_rows(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as con:
        con.executescript(V1.read_text())
        con.execute("INSERT INTO devices(device_id,name) VALUES ('CHG-001','旧设备')")
        con.execute(
            "INSERT INTO diagnostic_events(event_type,received_at,summary) VALUES ('conflict','2026-09-22T08:10:00.000000Z','保留证据')"
        )
    db = database(path)
    try:
        await db.initialize()
        async with db.sessions() as session:
            assert (
                await session.execute(text("SELECT name FROM devices WHERE device_id='CHG-001'"))
            ).scalar() == "旧设备"
            assert (
                await session.execute(text("SELECT summary FROM diagnostic_events"))
            ).scalar() == "保留证据"
            assert (
                await session.execute(text("SELECT count(*) FROM schema_migrations"))
            ).scalar() == 7
            assert (await session.execute(text("PRAGMA foreign_key_check"))).all() == []
        await db.initialize()
        async with db.sessions() as session:
            assert (
                await session.execute(text("SELECT count(*) FROM schema_migrations"))
            ).scalar() == 7
    finally:
        await db.close()


async def test_migration_checksum_tampering_rejected(tmp_path):
    db = database(tmp_path / "tampered.db")
    try:
        await db.initialize()
        async with db.sessions.begin() as session:
            await session.execute(
                text("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
            )
        with pytest.raises(RuntimeError, match="checksum"):
            await db.initialize()
    finally:
        await db.close()


async def test_failed_migration_rolls_back_ddl_and_version(tmp_path):
    from backend.app.migrations import DIRECTORY, migrate

    directory = tmp_path / "scripts"
    directory.mkdir()
    for source in DIRECTORY.glob("*.sql"):
        (directory / source.name).write_bytes(source.read_bytes())
    (directory / "008_failure.sql").write_text(
        "CREATE TABLE must_rollback(id INTEGER);\nINSERT INTO missing_table VALUES (1);\n"
    )
    db = database(tmp_path / "failure.db")
    try:
        async with db.engine.connect() as con:
            with pytest.raises(Exception, match="missing_table"):
                await migrate(con, directory)
            assert (
                await con.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")
            ).all() == []
    finally:
        await db.close()


async def test_schema_matches_orm(tmp_path):
    from sqlalchemy import inspect

    from backend.app.models import Base

    db = database(tmp_path / "schema.db")
    try:
        await db.initialize()
        async with db.engine.connect() as con:

            def compare(sync):
                inspector = inspect(sync)
                for table in Base.metadata.tables.values():
                    columns = {
                        column["name"]: column for column in inspector.get_columns(table.name)
                    }
                    assert set(columns) == set(table.columns.keys()), table.name
                    for expected in table.columns:
                        actual = columns[expected.name]
                        assert actual["nullable"] == expected.nullable, (table.name, expected.name)
                        assert str(actual["type"]) == str(expected.type), (
                            table.name,
                            expected.name,
                        )
                    actual_fks = {
                        (
                            tuple(f["constrained_columns"]),
                            f["referred_table"],
                            tuple(f["referred_columns"]),
                        )
                        for f in inspector.get_foreign_keys(table.name)
                    }
                    expected_fks = {
                        (
                            tuple(c.parent.name for c in f.elements),
                            f.referred_table.name,
                            tuple(c.column.name for c in f.elements),
                        )
                        for f in table.foreign_key_constraints
                    }
                    assert actual_fks == expected_fks, table.name
                    assert {i["name"] for i in inspector.get_indexes(table.name)} == {
                        i.name for i in table.indexes
                    }

            await con.run_sync(compare)
    finally:
        await db.close()


def test_backup_includes_wal_and_restore_refuses_overwrite(tmp_path):
    from backend.app.migrations.backup import backup_database, restore_database

    path = tmp_path / "source.db"
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, body TEXT)")
        con.execute("INSERT INTO evidence VALUES (1,'committed in WAL')")
        con.commit()
        backup = backup_database(path, tmp_path / "backup")
        restored = tmp_path / "restored.db"
        restore_database(backup, restored)
        with sqlite3.connect(restored) as restored_con:
            assert (
                restored_con.execute("SELECT body FROM evidence").fetchone()[0]
                == "committed in WAL"
            )
        with pytest.raises(FileExistsError):
            restore_database(backup, restored)
        assert con.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1


async def test_legacy_evidence_digest_unchanged(tmp_path):
    import hashlib
    import json

    from backend.app.migrations import migrate

    path = tmp_path / "evidence.db"
    with sqlite3.connect(path) as con:
        con.executescript(V1.read_text())
        con.execute("INSERT INTO devices(device_id,name) VALUES ('CHG-001','original')")
        con.execute(
            "INSERT INTO telemetry VALUES (1,'msg','CHG-001','boot',1,1,'2026-09-22T08:10:00.000000Z','2026-09-22T08:10:00.000000Z',72,400,50,20,'charging')"
        )
        con.execute("UPDATE devices SET latest_telemetry_id=1 WHERE device_id='CHG-001'")
        con.execute(
            "INSERT INTO agent_runs VALUES ('run','request','hash','question',1,'completed','answer','2026-09-22T08:10:00.000000Z',NULL,NULL,'[]','[]')"
        )
        con.execute(
            "INSERT INTO tool_calls VALUES ('tool','provider',1,'run','get_device_status','{}','{\"sample_id\":1}','succeeded','2026-09-22T08:10:00.000000Z',1,NULL)"
        )
        con.execute(
            "INSERT INTO work_orders VALUES ('order','CHG-001','OVERHEAT','OPEN','{\"tool_call_id\":\"tool\",\"sample_id\":1}','run','2026-09-22T08:10:00.000000Z')"
        )
        columns = {
            table: [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            for table in ("devices", "telemetry", "agent_runs", "tool_calls", "work_orders")
        }

        def digest(connection):
            rows = {
                table: connection.execute(
                    f"SELECT {','.join(names)} FROM {table} ORDER BY 1"
                ).fetchall()
                for table, names in columns.items()
            }
            return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()

        before = digest(con)
    db = database(path)
    try:
        async with db.engine.connect() as connection:
            await migrate(connection)
        with sqlite3.connect(path) as con:
            assert digest(con) == before
            assert con.execute("SELECT session_id,meter_total_wh FROM telemetry").fetchone() == (
                None,
                None,
            )
            assert con.execute("SELECT status FROM work_orders").fetchone()[0] == "OPEN"
    finally:
        await db.close()


async def test_unknown_legacy_schema_refused_without_mutation(tmp_path):
    path = tmp_path / "unknown.db"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE other(id INTEGER)")
    db = database(path)
    try:
        with pytest.raises(RuntimeError, match="Unrecognized legacy"):
            await db.initialize()
        with sqlite3.connect(path) as con:
            assert con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
                ("other",)
            ]
    finally:
        await db.close()


def test_migration_cli_offline_backup_restore(tmp_path):
    import json
    import subprocess
    import sys

    path = tmp_path / "cli.db"

    def run(*args):
        return subprocess.run(
            [sys.executable, "scripts/migrate.py", *map(str, args)], capture_output=True, text=True
        )

    assert run("--apply", "--database", path, "--backup-dir", tmp_path / "initial").returncode == 0
    result = run("--check", "--database", path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["version"] == 7
    assert run("--apply", "--database", path, "--backup-dir", tmp_path / "backup").returncode == 0
    restored = tmp_path / "restored.db"
    assert (
        run("--restore", tmp_path / "backup/database.sqlite3", "--destination", restored).returncode
        == 0
    )
    assert (
        run("--restore", tmp_path / "backup/database.sqlite3", "--destination", restored).returncode
        == 1
    )
    with sqlite3.connect(path):
        assert run("--apply", "--database", path, "--backup-dir", tmp_path / "busy").returncode == 1
    assert not (tmp_path / "busy").exists()
