import asyncio

from api import run_api_async


def main() -> None:
    asyncio.run(run_api_async())


if __name__ == "__main__":
    main()
