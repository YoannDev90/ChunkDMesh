
"""Entrypoint to run the FastAPI app with Uvicorn.

This module imports the `app` object directly and runs Uvicorn with
`reload=False`. If you want automatic reload during development, run
Uvicorn from the CLI so the process can import the package by name:

    uvicorn server.api:app --host 0.0.0.0 --port 8000 --reload

Running `python server/main.py` previously failed with `ModuleNotFoundError`
when Uvicorn attempted to reload by module name; importing the app object
avoids that issue.
"""

import asyncio
from api import run_api_async


def main() -> None:
    asyncio.run(run_api_async())


if __name__ == "__main__":
    main()

