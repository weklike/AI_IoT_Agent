"""Consistent, checksummed SQLite backups. Restore only ever creates a new path."""

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def validate(connection: sqlite3.Connection) -> int:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Backup integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("Backup foreign key check failed")
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name='schema_migrations'"
    ).fetchone()
    return (
        connection.execute("SELECT coalesce(max(version),0) FROM schema_migrations").fetchone()[0]
        if exists
        else 0
    )


def backup_database(source: Path, directory: Path) -> Path:
    source = source.resolve(strict=True)
    directory.mkdir(parents=True, exist_ok=False)
    destination = directory / "database.sqlite3"
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=1) as reader:
        with sqlite3.connect(destination) as writer:
            reader.backup(writer)
            version = validate(writer)
    manifest = {
        "source": str(source),
        "version": version,
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination


def restore_database(backup: Path, destination: Path) -> None:
    backup = backup.resolve(strict=True)
    manifest = json.loads((backup.parent / "manifest.json").read_text())
    if hashlib.sha256(backup.read_bytes()).hexdigest() != manifest["sha256"]:
        raise RuntimeError("Backup checksum mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also refuses a symlink or an existing empty target.
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True) as reader:
            if validate(reader) != manifest["version"]:
                raise RuntimeError("Backup version mismatch")
            with sqlite3.connect(destination) as writer:
                reader.backup(writer)
                validate(writer)
    except BaseException:
        destination.unlink()
        raise
