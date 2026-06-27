import asyncio

from db import init_db
from api import run_api
from logging_utils import setup_logging
from tasker import fill_tasks_table

async def main() -> None:
    """
    Launch the API server. This function is the entry point of the application.
    Load tasks into the database if needed.

    """
    setup_logging()
    await init_db()
    from config import Config
    config = Config()
    await config.validate()
    await fill_tasks_table(config)
    await run_api()




if __name__ == "__main__":
    asyncio.run(main())
