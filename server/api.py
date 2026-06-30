"""FastAPI entrypoint for ChunkDMesh orchestrator.

Thin shell: lifespan, middleware, router includes, run_api().
"""

import asyncio
import logging
import os
import time as _time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from constants import HEARTBEAT_TIMEOUT_SECONDS
from db import Batch, Client, get_db_session
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from routes import admin, assets, auth, client, map, tasks
from sqlalchemy import select

logger = logging.getLogger(__name__)

_SRV = Path(__file__).resolve().parent
_ROOT = _SRV.parent


async def _sweep_dead_clients():
    while True:
        try:
            await asyncio.sleep(30)
            async with get_db_session() as session:
                from datetime import datetime as _dt
                from datetime import timezone as _tz

                cutoff = _time.time() - HEARTBEAT_TIMEOUT_SECONDS
                cutoff_dt = _dt.fromtimestamp(cutoff, tz=_tz.utc)

                dead_result = await session.execute(
                    select(Client).where(
                        Client.last_seen.isnot(None),
                        Client.last_seen < cutoff_dt,
                    )
                )
                dead_clients = dead_result.scalars().all()

                for dead_client in dead_clients:
                    batch_result = await session.execute(
                        select(Batch).where(
                            Batch.assigned_to == dead_client.id,
                            Batch.status.in_(["assigned", "working"]),
                        )
                    )
                    stuck_batches = batch_result.scalars().all()
                    for batch in stuck_batches:
                        batch.status = "pending"
                        batch.assigned_to = None
                        logger.warning(
                            "Reassigning batch %s from dead client %s",
                            batch.id,
                            dead_client.id,
                        )

                if dead_clients:
                    await session.commit()
        except Exception:
            logger.exception("Dead client sweeper error")


@asynccontextmanager
async def lifespan(app_instance):
    task = asyncio.create_task(_sweep_dead_clients())
    yield
    task.cancel()


app = FastAPI(
    title="ChunkDMesh Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

FAVICON_PATH = _SRV / "config" / "favicon.ico"


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    t0 = _time.monotonic()
    resp = await call_next(request)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("%s %s -> %s (%sms)", request.method, request.url.path, resp.status_code, f"{elapsed_ms:.0f}")
    return resp


app.include_router(auth.router)
app.include_router(client.router)
app.include_router(tasks.router)
app.include_router(assets.router)
app.include_router(admin.router)
app.include_router(map.router)


@app.get("/")
async def root(request: Request):
    return JSONResponse({"project": "ChunkDMesh", "message": "Welcome to ChunkDMesh API"})


@app.get("/health")
async def health(request: Request):
    return JSONResponse({"status": "ok"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON_PATH, media_type="image/x-icon")


async def run_api():
    root_logger = logging.getLogger()
    host = os.environ.get("CHUNKMESH_HOST", "0.0.0.0")
    port = int(os.environ.get("CHUNKMESH_PORT", "8000"))

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _uvlog = logging.getLogger(name)
        _uvlog.handlers = root_logger.handlers[:]
        _uvlog.setLevel(root_logger.level)
        _uvlog.propagate = False

    await server.serve()


if __name__ == "__main__":
    uvicorn.run(app)
