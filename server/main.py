
"""Entrypoint to run the FastAPI app with Uvicorn.

This module imports the `app` object directly and runs Uvicorn with
`reload=False`. If you want automatic reload during development, run
Uvicorn from the CLI so the process can import the package by name:

    uvicorn server.api:app --host 0.0.0.0 --port 8000 --reload

Running `python server/main.py` previously failed with `ModuleNotFoundError`
when Uvicorn attempted to reload by module name; importing the app object
avoids that issue.
"""

import uvicorn

from server.api import app


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()

