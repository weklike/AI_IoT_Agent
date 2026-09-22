"""Initialize an empty local database. No reset/delete/replay operation exists here."""

import argparse
import asyncio

from sqlalchemy import text

from backend.app.config import Settings
from backend.app.db import Database


async def initialize_empty(settings: Settings) -> str:
    db = Database(settings)
    try:
        async with db.sessions() as session:
            tables = (
                (await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")))
                .scalars()
                .all()
            )
            if tables:
                if "devices" not in tables:
                    raise RuntimeError(
                        "Existing database is not an initialized charge-ops database; left unchanged"
                    )
                count = (await session.execute(text("SELECT count(*) FROM devices"))).scalar()
                if count != 3:
                    raise RuntimeError(
                        "Existing database has unexpected device count; left unchanged"
                    )
                return "already_initialized"
        await db.initialize()
        return "created"
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["demo"], required=True)
    parser.parse_args()
    settings = Settings(llm_mode="fixture")
    result = asyncio.run(initialize_empty(settings))
    print(
        result + ": no telemetry or work orders were deleted; use the simulator for current samples"
    )


if __name__ == "__main__":
    main()
