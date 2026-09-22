"""Checked, transactional SQLite migrations; also adopts the exact legacy schema."""

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncConnection

DIRECTORY = Path(__file__).parent


def statements(script: str) -> list[str]:
    result, pending = [], ""
    for line in script.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            result.append(pending.strip())
            pending = ""
    if pending.strip():
        raise RuntimeError("Incomplete migration SQL")
    return result


def schema_signature(connection: sqlite3.Connection) -> list[tuple]:
    return connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
    ).fetchall()


async def migrate(connection: AsyncConnection, directory: Path = DIRECTORY) -> None:
    files = sorted(directory.glob("[0-9][0-9][0-9]_*.sql"))
    versions = [int(file.name[:3]) for file in files]
    if not versions or versions != list(range(1, len(files) + 1)):
        raise RuntimeError("Migration versions must be contiguous from 1")
    scripts = [(version, file.read_text()) for version, file in zip(versions, files)]
    await connection.exec_driver_sql("BEGIN EXCLUSIVE")
    try:
        names = set(
            (
                await connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ).scalars()
        )
        adopted = False
        if names and "schema_migrations" not in names:
            with sqlite3.connect(":memory:") as reference:
                reference.executescript(scripts[0][1])
                expected = schema_signature(reference)
            actual = [
                tuple(row)
                for row in (
                    await connection.exec_driver_sql(
                        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                    )
                ).all()
            ]

            # SQLite retains harmless SQL whitespace; normalize it for adoption only.
            def normalize(rows):
                return [(a, b, c, " ".join(d.split()) if d else d) for a, b, c, d in rows]

            if normalize(actual) != normalize(expected):
                raise RuntimeError("Unrecognized legacy schema; migration refused")
            adopted = True
        await connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY NOT NULL, checksum VARCHAR NOT NULL, applied_at VARCHAR(27) NOT NULL)"
        )
        applied = dict(
            (
                await connection.exec_driver_sql(
                    "SELECT version,checksum FROM schema_migrations ORDER BY version"
                )
            ).all()
        )
        if list(applied) != versions[: len(applied)]:
            raise RuntimeError("Unknown or noncontiguous migration version")
        for version, script in scripts:
            checksum = hashlib.sha256(script.encode()).hexdigest()
            if version in applied:
                if applied[version] != checksum:
                    raise RuntimeError(f"Migration {version} checksum mismatch")
                continue
            if not (adopted and version == 1):
                for statement in statements(script):
                    await connection.exec_driver_sql(statement)
            await connection.exec_driver_sql(
                "INSERT INTO schema_migrations VALUES (?,?,?)",
                (
                    version,
                    checksum,
                    datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
                ),
            )
        if (await connection.exec_driver_sql("PRAGMA foreign_key_check")).all():
            raise RuntimeError("Migration foreign key check failed")
        if (await connection.exec_driver_sql("PRAGMA integrity_check")).scalar() != "ok":
            raise RuntimeError("Migration integrity check failed")
        await connection.commit()
    except BaseException:
        await connection.rollback()
        raise
