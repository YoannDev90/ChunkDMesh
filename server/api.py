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
from routes import admin, assets, auth, client, map, tasks, tiles
from sqlalchemy import func, select
from state import server_state

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
                        server_state.log("♻", f"Reassigned batch {batch.id} from dead client {dead_client.id}")
                        logger.warning(
                            "Reassigning batch %s from dead client %s",
                            batch.id,
                            dead_client.id,
                        )

                if dead_clients:
                    await session.commit()
        except Exception:
            logger.exception("Dead client sweeper error")


async def _update_state_loop():
    """Periodically poll DB and push counts into server_state for TUI."""
    while True:
        try:
            await asyncio.sleep(3)
            async with get_db_session() as session:
                counts = {}
                for status in ("pending", "assigned", "working", "completed", "validated"):
                    result = await session.execute(select(func.count(Batch.id)).where(Batch.status == status))
                    counts[status] = result.scalar() or 0
                server_state.update_task_counts(
                    pending=counts["pending"],
                    assigned=counts["assigned"],
                    working=counts["working"],
                    completed=counts["completed"],
                    validated=counts["validated"],
                )

                client_count = await session.execute(select(func.count(Client.id)))
                server_state.update_clients(client_count.scalar() or 0)
        except Exception:
            logger.exception("State update loop error")


@asynccontextmanager
async def lifespan(app_instance):
    # Load world config for TUI display
    from config import Config

    try:
        cfg = Config()
        await cfg.validate()
        server_state.set_world_config(
            {
                "world_name": cfg.world_name,
                "minecraft_version": cfg.minecraft_version,
                "minecraft_loader": cfg.minecraft_loader,
                "seed": cfg.seed,
                "shape": cfg.shape,
                "dimension": cfg.dimension,
                "radius": cfg.radius,
            }
        )
    except Exception:
        logger.exception("Failed to load world config for TUI")

    sweep_task = asyncio.create_task(_sweep_dead_clients())
    state_task = asyncio.create_task(_update_state_loop())
    server_state.log("★", "Server started")
    yield
    sweep_task.cancel()
    state_task.cancel()


app = FastAPI(
    title="ChunkDMesh Orchestrator",
    version="0.1.0",
    lifespan=lifespan,
)

FAVICON_PATH = _SRV / "config" / "favicon.ico"


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    resp = await call_next(request)
    server_state.record_request(request.url.path, resp.status_code)
    return resp


app.include_router(auth.router)
app.include_router(client.router)
app.include_router(tasks.router)
app.include_router(assets.router)
app.include_router(admin.router)
app.include_router(map.router)
app.include_router(tiles.router)


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
