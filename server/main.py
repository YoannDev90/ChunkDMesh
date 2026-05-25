import asyncio
import logging
import logging.config
import uvicorn

import config

# Initialisation immédiate du logging avant tout import qui pourrait créer un logger
logging.config.dictConfig(config.LOGGING_CONFIG)
LOGGER = logging.getLogger(config.LOGGER_NAME)

from api import app
from database import Database, Type
from world_gen import initialize_world_gen, populate_tasks


async def initialize_database():
    """Initialise le schéma de la base de données."""
    async with Database(config.DB_PATH) as db:
        await db.initialize_schema()
        tables = await db.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table';", type=Type.LIST
        )
        return tables


async def main() -> None:
    print(config.ASCII_ART)
    LOGGER.info("ChunkDMesh orchestrator is ready.")

    tables = await initialize_database()
    LOGGER.info(f"Database initialized (Tables: {tables}).")

    # Gestion de la configuration du monde
    if config.ACTIVE_CONFIG_PATH.exists():
        LOGGER.info(
            f"Chargement de la configuration existante : {config.ACTIVE_CONFIG_PATH}"
        )
        world_conf = config.load_config()
        # On ne passe plus par asyncio.to_thread car populate_tasks est déjà async
        asyncio.create_task(
            populate_tasks(
                world_conf.center if hasattr(world_conf, "center") else "spawn",
                world_conf.radius if hasattr(world_conf, "radius") else 0,
            )
        )
    else:
        LOGGER.info("Aucune configuration trouvée. Lancement de la TUI...")
        await initialize_world_gen()

    # Démarrage de l'API avec uvicorn
    server_config = uvicorn.Config(
        app, host=config.HOST, port=config.PORT, log_level="info"
    )
    server = uvicorn.Server(server_config)

    LOGGER.info(f"ChunkDMesh API is running on http://{config.HOST}:{config.PORT}")
    await server.serve()


if __name__ == "__main__":
    import sys

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
