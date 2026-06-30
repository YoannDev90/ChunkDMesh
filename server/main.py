import asyncio

from api import run_api
from db import init_db
from logging_utils import setup_logging
from tasker import fill_tasks_table


async def main() -> None:
    setup_logging()
    await init_db()
    from config import Config

    config = Config()
    await config.validate()
    await fill_tasks_table(config)
    await run_api()


if __name__ == "__main__":
    asyncio.run(main())
