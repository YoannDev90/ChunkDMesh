import asyncio
import logging
import logging.config

from api import start_api

import config

logging.config.dictConfig(config.LOGGING_CONFIG)
LOGGER = logging.getLogger(config.LOGGER_NAME)


async def main() -> None:
    print(config.ASCII_ART)
    LOGGER.info("ChunkDMesh orchestrator is ready.")
    await start_api()


if __name__ == "__main__":
    asyncio.run(main())
