"""Offline migration/restore entry point. Never loads or prints model credentials."""

import argparse
import asyncio
import json
import os
import sqlite3
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.config import Settings
from backend.app.migrations import migrate
from backend.app.migrations.backup import backup_database, restore_database, validate


def require_offline(path: Path) -> None:
    """Conservatively reject any other process with the database or WAL open."""
    targets = {str(path.resolve()) + suffix for suffix in ("", "-wal", "-shm")}
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            for descriptor in (process / "fd").iterdir():
                try:
                    if os.readlink(descriptor) in targets:
                        raise RuntimeError(
                            f"Database is open by process {process.name}; stop its service first"
                        )
                except FileNotFoundError:
                    continue
        except (PermissionError, FileNotFoundError):
            continue


async def apply(path: Path) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///" + str(path))
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            await connection.exec_driver_sql("PRAGMA busy_timeout=1000")
            await connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            await connection.commit()
            await migrate(connection)
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument(
        "--restore", type=Path, help="Backup database.sqlite3 with sibling manifest.json"
    )
    parser.add_argument("--database", type=Path)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    try:
        if args.restore:
            if not args.destination:
                parser.error("--restore requires --destination (a new path)")
            require_offline(args.destination)
            restore_database(args.restore, args.destination)
            print(json.dumps({"status": "restored", "destination": str(args.destination)}))
            return 0
        path = args.database
        if path is None:
            url = make_url(Settings().database_url)
            if (
                url.drivername != "sqlite+aiosqlite"
                or not url.database
                or url.database == ":memory:"
            ):
                raise ValueError("A local SQLite file is required")
            path = Path(url.database)
        path = path.resolve()
        if args.check:
            if not path.exists():
                print(json.dumps({"version": 0, "exists": False}))
            else:
                with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1) as con:
                    print(json.dumps({"version": validate(con), "exists": True}))
            return 0
        if not args.backup_dir:
            parser.error("--apply requires a new --backup-dir")
        require_offline(path)
        if path.exists():
            backup_database(path, args.backup_dir)
        else:
            args.backup_dir.mkdir(parents=True, exist_ok=False)
            (args.backup_dir / "manifest.json").write_text(
                json.dumps({"version": 0, "exists": False}) + "\n"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(apply(path))
        print(json.dumps({"status": "applied", "backup_dir": str(args.backup_dir)}))
        return 0
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
