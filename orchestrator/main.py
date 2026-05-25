import asyncio
import logging
import logging.config
from typing import List, Tuple

import config

# Initialisation immédiate du logging avant tout import qui pourrait créer un logger
logging.config.dictConfig(config.LOGGING_CONFIG)
LOGGER = logging.getLogger(config.LOGGER_NAME)

from api import start_api  # noqa: E402
from database import Database, Type  # noqa: E402


def initialize_database() -> List[Tuple[str]]:
    """Initialise la base dans un thread dédié pour éviter de bloquer l'event loop."""
    db = Database(config.DB_PATH)
    db.connect()
    db.initialize_schema()
    tables = db.execute_query(
        "SELECT name FROM sqlite_master WHERE type='table';", type=Type.LIST
    )
    db.close()
    return tables


async def main() -> None:
    print(config.ASCII_ART)
    LOGGER.info("ChunkDMesh orchestrator is ready.")

    tables = await asyncio.to_thread(initialize_database)
    LOGGER.info(f"Database initialized (Tables: {tables}).")

    host, port, api_task = await start_api()
    LOGGER.info(f"ChunkDMesh API is running on http://{host}:{port}")

    try:
        await api_task
    except asyncio.CancelledError:
        LOGGER.info("API task cancelled.")


if __name__ == "__main__":
    import sys

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
