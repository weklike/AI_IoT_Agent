"""Check or atomically refresh the fixed repository knowledge corpus in a migrated database."""

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import Settings
from backend.app.db import Database
from backend.app.knowledge.index import KnowledgeIndex


async def run(apply: bool) -> int:
    settings = Settings()
    url = make_url(settings.database_url)
    if not url.database or not Path(url.database).is_file():
        print(
            json.dumps(
                {"status": "BLOCKED", "reason": "Migrate the configured local database first"}
            )
        )
        return 2
    db = Database(settings)
    index = KnowledgeIndex(db)
    try:
        changed = await index.refresh(check_only=not apply)
        ready = index.available
        print(
            json.dumps(
                {
                    "status": "PASS" if ready else "NOT_RUN",
                    "changed": changed if apply else False,
                    "rebuild_required": not ready,
                },
                ensure_ascii=False,
            )
        )
        return 0 if ready else 1
    except (ValueError, OSError, SQLAlchemyError) as error:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error_type": type(error).__name__,
                    "reason": "Knowledge validation or indexing failed; previous transaction retained",
                }
            )
        )
        return 1
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
