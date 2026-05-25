import asyncio
import logging
import logging.config
from typing import List, Tuple

from api import start_api
from database import Database

import config

logging.config.dictConfig(config.LOGGING_CONFIG)
LOGGER = logging.getLogger(config.LOGGER_NAME)


def initialize_database() -> List[Tuple[str]]:
    """Initialise la base dans un thread dédié pour éviter de bloquer l'event loop."""
    db = Database(config.DB_PATH)
    db.connect()
    db.initialize_schema()
    tables = db.execute_query("SELECT name FROM sqlite_master WHERE type='table';")
    db.close()
    return tables


async def main() -> None:
    print(config.ASCII_ART)
    LOGGER.info("ChunkDMesh orchestrator is ready.")

    # On initialise la base d'abord
    tables = await asyncio.to_thread(initialize_database)
    LOGGER.info("Database initialized.")
    LOGGER.debug("Available tables: %s", tables)

    # Puis on lance l'API
    host, port, api_task = await start_api()
    LOGGER.info("ChunkDMesh API is running on http://%s:%s", host, port)

    try:
        await api_task
    except asyncio.CancelledError:
        LOGGER.info("API task cancelled.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt de l'orchestrateur...")
