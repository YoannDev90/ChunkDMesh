"""FastAPI API entrypoint for ChunkDMesh orchestrator.

- GET / : basic project info
- GET /docs : API documentation (OpenAPI spec)
- GET /health : health check
- POST /auth/login : Le client envoie ses capacités (CPU, RAM disponible) et reçoit un token JWT.
- GET /assets/mods.zip : Streaming de l'archive des mods (avec support du header `Range`).
- GET /assets/config.json : Configuration spécifique de Chunky pour cette session.
- GET /tasks/batch : Récupère un lot de chunks. Le serveur marque le batch comme `ASSIGNED`.
- POST /tasks/submit : Envoie les hashes SHA-256 de chaque chunk généré.
- PUT /tasks/upload/{batch_id} : Upload binaire des données de chunks (compressées en Zstd).
- GET /admin/heatmap : Renvoie une matrice de l'état du monde pour le dashboard.
"""

import asyncio
import datetime
import hashlib
import logging
import math
import os
from pathlib import Path
from typing import Dict, Generator, Optional

import uvicorn
import zstd
from config import Config
from db import Batch, Client, get_db_session
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from jwt import PyJWTError, decode, encode
from pydantic import BaseModel

logger = logging.getLogger(__name__)
from sqlalchemy import select
from storage_manager import ChunkStorage

app = FastAPI(
    title="ChunkDMesh Orchestrator", version="0.1.0"
)
FAVICON_PATH = Path(__file__).resolve().parent / "config" / "favicon.ico"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    import time as _time
    t0 = _time.monotonic()
    resp = await call_next(request)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("%s %s -> %s (%sms)", request.method, request.url.path,
                resp.status_code, f"{elapsed_ms:.0f}")
    return resp


async def run_api():
    import logging as _logging
    root_logger = _logging.getLogger()

    config = uvicorn.Config(
        app, host="0.0.0.0", port=8000, log_level="info",
        log_config=None, access_log=False,
    )
    server = uvicorn.Server(config)

    # Route uvicorn loggers through our formatter
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _uvlog = _logging.getLogger(name)
        _uvlog.handlers = root_logger.handlers[:]
        _uvlog.setLevel(root_logger.level)
        _uvlog.propagate = False

    await server.serve()


def get_secret_key():
    key_path = Path(__file__).resolve().parent / "config" / "key.pem"
    if key_path.exists():
        return key_path.read_text().strip()
    
    import secrets
    key = secrets.token_hex(64)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(key)
    return key


async def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    token = authorization.split(" ")[1]
    sk_key = get_secret_key()
    try:
        payload = decode(token, sk_key, algorithms=["HS256"])
        return payload
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def file_stream_generator(
    path: str, chunk_size: int = 1024 * 64
) -> Generator[bytes, None, None]:
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk


class LoginRequest(BaseModel):
    power_score: float

class SubmitTasksRequest(BaseModel):
    batch_id: int
    chunk_hashes: Dict[str, str]  # {"chunk_x_z": "sha256hash"}


@app.get("/")
async def root(request: Request):
    return JSONResponse(
        {
            "project": "ChunkDMesh",
            "message": "Welcome to ChunkDMesh API",
        }
    )


@app.get("/health")
async def health(request: Request):
    return JSONResponse({"status": "ok"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse(FAVICON_PATH, media_type="image/x-icon")


@app.post("/auth/login")
async def login(login_request: LoginRequest, request: Request):
    sk_key = get_secret_key()
    async with get_db_session() as session:
        client = Client(
            token=None,
            ip=request.client.host,
            power_score=login_request.power_score,
        )
        session.add(client)
        await session.flush()

        payload = {
            "client_id": client.id,
            "client_ip": request.client.host,
            "timestamp": int(datetime.datetime.now().timestamp()),
            "power_score": login_request.power_score,
        }
        jwt_token = encode(payload, sk_key, algorithm="HS256")
        client.token = jwt_token
        await session.commit()

    return JSONResponse({"token": jwt_token})


class BenchmarkRequest(BaseModel):
    chunks_per_second: float
    duration_seconds: float
    chunks_generated: int


@app.post("/benchmark")
async def submit_benchmark(req: BenchmarkRequest, request: Request, token_data: dict = Depends(verify_token)):
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")

    score = req.chunks_per_second

    async with get_db_session() as session:
        result = await session.execute(
            select(Client).where(Client.id == client_id).limit(1)
        )
        client = result.scalar_one_or_none()
        if client:
            client.benchmark_score = score
            await session.commit()

    logger.info("benchmark submitted: client=%s chunks/s=%.2f", client_id, score)

    return JSONResponse({
        "status": "accepted",
        "chunks_per_second": score,
    })


@app.get("/assets/mods.zip")
async def get_mods(request: Request, token_data: dict = Depends(verify_token)):
    zip_path = "data/mods.zip"
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Mods not found")
    filename = os.path.basename(zip_path)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        file_stream_generator(zip_path), media_type="application/zip", headers=headers
    )


@app.get("/assets/config.json")
async def get_config(request: Request, token_data: dict = Depends(verify_token)):
    from config import Config

    config = Config()
    await config.validate()
    config_dict = config.to_dict()
    return JSONResponse(config_dict)


@app.get("/tasks/batch")
async def get_batch(request: Request, token_data: dict = Depends(verify_token)):
    from tasker import attribute_tasks_to_client
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")
    try:
        batch_id, region_coords = await attribute_tasks_to_client(client_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="No tasks available")
    batch = {
        "batch_id": batch_id,
        "regions": [{"region_x": rx, "region_z": rz} for rx, rz in region_coords],
    }
    return JSONResponse(batch)


STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "storage"


@app.post("/tasks/submit")
async def submit_tasks(submit_tasks_request: SubmitTasksRequest, request: Request, token_data: dict = Depends(verify_token)):
    batch_id = submit_tasks_request.batch_id
    chunk_hashes = submit_tasks_request.chunk_hashes

    results = {}
    storage = ChunkStorage()

    for filename, declared_hash in chunk_hashes.items():
        # Use cached hash from validation table if available
        cached_hash = None
        async with get_db_session() as session:
            from db import Validation
            v_result = await session.execute(
                select(Validation).where(
                    Validation.batch_id == batch_id,
                    Validation.storage_path == f"{batch_id}/{filename}",
                ).limit(1)
            )
            v = v_result.scalar_one_or_none()
            if v:
                cached_hash = v.file_hash

        if cached_hash:
            actual_hash = cached_hash
        else:
            data = storage.read_mca(batch_id, filename)
            if data is None:
                results[filename] = {"status": "missing", "declared_hash": declared_hash}
                continue
            actual_hash = hashlib.sha256(data).hexdigest()

        if actual_hash == declared_hash:
            results[filename] = {"status": "valid", "hash": actual_hash}
        else:
            results[filename] = {
                "status": "mismatch",
                "declared_hash": declared_hash,
                "actual_hash": actual_hash,
            }

    valid_count = sum(1 for r in results.values() if r["status"] == "valid")
    total_count = len(results)
    all_valid = valid_count == total_count

    logger.info("hash validation: batch=%s valid=%s/%s", batch_id, valid_count, total_count)

    async with get_db_session() as session:
        batch_result = await session.execute(
            select(Batch).where(Batch.id == batch_id).limit(1)
        )
        batch = batch_result.scalar_one_or_none()

        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        batch.status = "completed" if all_valid else "hash_error"

        from config import Config
        config = Config()

        if config.verification and all_valid:
            other_result = await session.execute(
                select(Batch).where(
                    Batch.id != batch_id,
                    Batch.region_x == batch.region_x,
                    Batch.region_z == batch.region_z,
                    Batch.status == "completed",
                ).limit(1)
            )
            other_batch = other_result.scalar_one_or_none()

            if other_batch:
                match = True
                for filename, info in results.items():
                    if info["status"] != "valid":
                        continue
                    # Use cached hash instead of re-reading
                    other_hash = storage.get_mca_hash(other_batch.id, filename)
                    if not other_hash or other_hash != info["hash"]:
                        match = False
                        break

                if match:
                    batch.status = "validated"
                    other_batch.status = "validated"
                    logger.info("batch validated by redundancy: batch=%s other=%s",
                                batch_id, other_batch.id)
                else:
                    batch.status = "hash_error"
                    other_batch.status = "hash_error"
                    batch.retry_count += 1
                    other_batch.retry_count += 1
                    logger.warning("redundancy mismatch: batch=%s other=%s",
                                  batch_id, other_batch.id)

            elif batch.status == "completed":
                pass

        await session.commit()

    if all_valid:
        from s3_storage import create_storage_from_env
        s3 = create_storage_from_env()
        if s3:
            try:
                batch_dir = STORAGE_DIR / str(batch_id)
                s3.upload_batch(batch_dir, batch_id)
                logger.info("batch uploaded to S3: batch=%s", batch_id)
            except Exception as e:
                logger.error("S3 upload failed: batch=%s error=%s", batch_id, e)

    return JSONResponse({
        "status": batch.status,
        "batch_id": batch_id,
        "results": results,
    })


@app.put("/tasks/upload/{batch_id}")
async def upload_chunks(
    batch_id: int, request: Request, token_data: dict = Depends(verify_token)
):
    chunk_data = await request.body()
    try:
        decompressed_data = zstd.decompress(chunk_data)
        filename = request.headers.get("X-Filename", f"r.0.0.mca")

        # Dedup store + cache hash
        storage = ChunkStorage()
        sha256_hash, raw_size = storage.write_mca(
            batch_id, filename, decompressed_data
        )

        # Cache hash in DB for later verification (avoid re-read)
        async with get_db_session() as session:
            # Store hash in validation table immediately
            from db import Validation
            from sqlalchemy import select as sa_select
            existing = await session.execute(
                sa_select(Validation).where(
                    Validation.batch_id == batch_id,
                    Validation.file_hash == sha256_hash,
                )
            )
            if not existing.scalar_one_or_none():
                validation = Validation(
                    batch_id=batch_id,
                    client_id=0,  # Unknown at upload time
                    file_hash=sha256_hash,
                    storage_path=f"{batch_id}/{filename}",
                )
                session.add(validation)

            batch_result = await session.execute(
                select(Batch).where(Batch.id == batch_id).limit(1)
            )
            batch = batch_result.scalar_one_or_none()
            if batch and batch.status == "assigned":
                batch.status = "working"
            await session.commit()

        logger.info("upload received: batch=%s file=%s hash=%s raw=%s compressed=%s",
                    batch_id, filename, sha256_hash, raw_size, len(chunk_data))

        return JSONResponse({
            "status": "received",
            "batch_id": batch_id,
            "filename": filename,
            "hash": sha256_hash,
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decompression failed: {str(e)}")


@app.put("/tasks/upload/tile/{batch_id}")
async def upload_tile(batch_id: int, request: Request, token_data: dict = Depends(verify_token)):
    from map_renderer import CACHE_DIR
    png_data = await request.body()
    filename = request.headers.get("X-Filename", "")
    scale_header = request.headers.get("X-Scale", "1")
    try:
        scale = int(scale_header)
    except ValueError:
        scale = 1

    if not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Filename must end with .png")
    parts = filename.replace(".png", "").split(".")
    if len(parts) != 3 or parts[0] != "r":
        raise HTTPException(status_code=400, detail="Filename must be r.{rx}.{rz}.png")
    rx, rz = int(parts[1]), int(parts[2])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"r.{rx}.{rz}.s{scale}.png"
    with open(out, "wb") as f:
        f.write(png_data)

    logger.info("tile uploaded: batch=%s region=%s,%s scale=%s", batch_id, rx, rz, scale)
    return JSONResponse({"status": "ok", "region": {"rx": rx, "rz": rz}, "scale": scale})


@app.get("/admin/heatmap")
async def get_heatmap(request: Request):
    async with get_db_session() as session:
        result = await session.execute(
            select(Batch.region_x, Batch.region_z, Batch.status, Batch.assigned_to)
        )
        rows = result.all()

    heatmap = [
        {"region_x": r.region_x, "region_z": r.region_z, "status": r.status, "assigned_to": r.assigned_to}
        for r in rows
    ]
    return JSONResponse({"regions": heatmap})


@app.get("/admin/map/regions")
async def get_map_regions(request: Request):
    """Return list of regions that have .mca files in storage (for map rendering)."""
    from pathlib import Path
    STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "storage"

    regions = []
    if STORAGE_DIR.exists():
        for bdir in sorted(STORAGE_DIR.iterdir(), key=lambda p: int(p.name)):
            if bdir.is_dir():
                for mca in bdir.glob("r.*.*.mca"):
                    parts = mca.stem.split(".")
                    if len(parts) == 3:
                        rx, rz = int(parts[1]), int(parts[2])
                        regions.append({"region_x": rx, "region_z": rz, "status": "available"})

    # Remove duplicates (same region in multiple batches)
    seen = set()
    unique_regions = []
    for r in regions:
        key = (r["region_x"], r["region_z"])
        if key not in seen:
            seen.add(key)
            unique_regions.append(r)

    return JSONResponse({"regions": unique_regions})


CLIENT_VERSION = "0.1.0"


@app.get("/client/version")
async def get_client_version(request: Request):
    return JSONResponse({
        "version": CLIENT_VERSION,
        "download_url": "/client/download",
    })


@app.get("/client/download")
async def download_client(request: Request):
    client_archive = Path(__file__).resolve().parent.parent / "client" / "chunkdmesh_client.tar.gz"
    if not client_archive.exists():
        raise HTTPException(status_code=404, detail="Client archive not found")
    return FileResponse(client_archive, filename="chunkdmesh_client.tar.gz")


@app.get("/admin/stats")
async def admin_stats(request: Request):
    from storage_manager import ChunkStorage
    from map_renderer import _HAS_RUST_TILER, CACHE_DIR

    storage = ChunkStorage()
    batches = storage.list_batches()

    blob_dir = storage.storage_dir / ".blobs"
    blob_count = 0
    blob_size_mb = 0.0
    if blob_dir.exists():
        blob_files = list(blob_dir.iterdir())
        blob_count = len(blob_files)
        blob_size_mb = round(sum(f.stat().st_size for f in blob_files) / (1024 * 1024), 1)

    async with get_db_session() as session:
        status_result = await session.execute(select(Batch.status))
        statuses = status_result.scalars().all()

    status_counts = {}
    for s in statuses:
        status_counts[s] = status_counts.get(s, 0) + 1

    cache_size_mb = 0.0
    cache_count = 0
    if CACHE_DIR.exists():
        cache_files = list(CACHE_DIR.iterdir())
        cache_count = len(cache_files)
        cache_size_mb = round(sum(f.stat().st_size for f in cache_files) / (1024 * 1024), 1)

    return JSONResponse({
        "storage": {
            "batch_dirs": len(batches),
            "blobs": blob_count,
            "blobs_size_mb": blob_size_mb,
            "total_size_mb": storage.total_size_mb(),
        },
        "database": {
            "total_batches": len(statuses),
            "by_status": status_counts,
        },
        "map_cache": {
            "files": cache_count,
            "size_mb": cache_size_mb,
        },
        "features": {
            "rust_tiler": _HAS_RUST_TILER,
        },
    })


@app.post("/admin/assemble")
async def assemble_world(request: Request):
    from config import Config
    from assembler import RegionAssembler

    config = Config()
    assembler = RegionAssembler(config.world_name)
    result = await assembler.assemble()
    progress = assembler.get_progress()

    # Auto-cleanup: remove batch storage dirs after successful assembly
    if result.get("assembled", 0) > 0:
        from storage_manager import ChunkStorage
        storage_cleanup = ChunkStorage().cleanup_after_assembly()
        result["storage_cleanup"] = storage_cleanup

    return JSONResponse({**result, **progress})


@app.get("/admin/progress")
async def get_progress(request: Request):
    from config import Config
    from assembler import RegionAssembler

    config = Config()
    assembler = RegionAssembler(config.world_name)
    progress = assembler.get_progress()

    async with get_db_session() as session:
        batch_result = await session.execute(
            select(Batch.status)
        )
        statuses = batch_result.scalars().all()

    status_counts = {}
    for s in statuses:
        status_counts[s] = status_counts.get(s, 0) + 1

    return JSONResponse({
        "files": progress,
        "batches": status_counts,
    })


@app.post("/admin/export")
async def export_world(request: Request):
    from config import Config
    from exporter import ExportManager

    config = Config()
    manager = ExportManager(config.world_name)

    try:
        archive_path = manager.export()
        return JSONResponse({
            "status": "exported",
            "archive": archive_path.name,
            "download": f"/admin/download/{archive_path.name}",
        })
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/admin/archives")
async def list_archives(request: Request):
    from config import Config
    from exporter import ExportManager

    config = Config()
    manager = ExportManager(config.world_name)
    archives = manager.list_archives()

    return JSONResponse({"archives": archives})


@app.post("/admin/torrent")
async def create_mods_torrent(request: Request):
    zip_path = Path("data/mods.zip")
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="mods.zip not found")

    try:
        from s3_storage import create_storage_from_env
        from p2p_server import create_torrent

        torrent_path = create_torrent(zip_path)

        storage = create_storage_from_env()
        download_url = None
        if storage:
            storage.upload_file(torrent_path, f"torrents/{torrent_path.name}")
            download_url = storage.presign_url(f"torrents/{torrent_path.name}")

        return JSONResponse({
            "status": "created",
            "torrent": torrent_path.name,
            "download_url": download_url,
        })
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/download/{filename}")
async def download_archive(filename: str, request: Request, token_data: dict = Depends(verify_token)):
    from config import Config
    from exporter import ExportManager

    config = Config()
    manager = ExportManager(config.world_name)
    archive_path = manager.exports_dir / filename

    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Archive not found")

    return FileResponse(
        archive_path,
        media_type="application/gzip",
        filename=filename,
    )


@app.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/admin/map", response_class=HTMLResponse)
async def map_view(request: Request):
    return templates.TemplateResponse(request, "map.html")


@app.get("/admin/progress/html")
async def get_progress_partial(request: Request):
    from config import Config
    from assembler import RegionAssembler

    config = Config()
    assembler = RegionAssembler(config.world_name)
    progress = assembler.get_progress()

    async with get_db_session() as session:
        batch_result = await session.execute(select(Batch.status))
        statuses = batch_result.scalars().all()

    counts = {"assigned": 0, "working": 0, "completed": 0, "validated": 0, "errors": 0}
    for s in statuses:
        if s in counts:
            counts[s] += 1
        elif s == "hash_error":
            counts["errors"] += 1

    return templates.TemplateResponse(request, "stats_partial.html", {
        "total_files": progress["total_files"],
        "total_size_mb": progress["total_size_mb"],
        **counts,
    })


@app.get("/admin/heatmap/html")
async def get_heatmap_partial(request: Request):
    async with get_db_session() as session:
        result = await session.execute(
            select(Batch.region_x, Batch.region_z, Batch.status)
        )
        rows = result.all()

    if not rows:
        regions = []
    else:
        min_x = min(r.region_x for r in rows)
        max_x = max(r.region_x for r in rows)
        min_z = min(r.region_z for r in rows)
        max_z = max(r.region_z for r in rows)

        grid = {}
        for r in rows:
            grid[(r.region_x, r.region_z)] = r.status

        regions = []
        for z in range(min_z, max_z + 1):
            for x in range(min_x, max_x + 1):
                status = grid.get((x, z), "pending")
                regions.append({"region_x": x, "region_z": z, "status": status})

    cols = max_x - min_x + 1 if rows else 1
    return templates.TemplateResponse(request, "heatmap_partial.html", {
        "regions": regions,
        "cols": cols,
    })


@app.get("/admin/map/render/{rx}/{rz}")
async def render_region_tile(rx: int, rz: int, request: Request, scale: int = 1):
    from map_renderer import (render_region_tile_cached,
                              STORAGE_DIR, cached_region_path)

    cache_path = cached_region_path(rx, rz, scale)
    if cache_path.exists():
        logger.info("tile served from cache: %s,%s s=%s", rx, rz, scale)
        return FileResponse(str(cache_path), media_type="image/png")

    if scale not in (1, 16):
        hi_cache = cached_region_path(rx, rz, 16)
        if hi_cache.exists():
            from PIL import Image
            img = Image.open(hi_cache)
            img = img.resize((512 * scale, 512 * scale), Image.LANCZOS)
            img.save(cache_path)
            logger.info("tile served from hi-cache: %s,%s s=%s", rx, rz, scale)
            return FileResponse(str(cache_path), media_type="image/png")

        lo_cache = cached_region_path(rx, rz, 1)
        if lo_cache.exists():
            from PIL import Image
            img = Image.open(lo_cache)
            img = img.resize((512 * scale, 512 * scale), Image.NEAREST)
            img.save(cache_path)
            logger.info("tile served from lo-cache scaled: %s,%s s=%s", rx, rz, scale)
            return FileResponse(str(cache_path), media_type="image/png")

    logger.warning("tile render fallback: %s,%s s=%s", rx, rz, scale)

    mca_path = None
    if STORAGE_DIR.exists():
        for bdir in sorted(STORAGE_DIR.iterdir(), key=lambda p: int(p.name)):
            candidate = bdir / f"r.{rx}.{rz}.mca"
            if candidate.exists():
                mca_path = candidate
                break

    if not mca_path:
        return JSONResponse({"error": f"Region r.{rx}.{rz}.mca not found"}, status_code=404)

    _RENDER_POOL = getattr(app.state, "_render_pool", None)
    if _RENDER_POOL is None:
        from concurrent.futures import ThreadPoolExecutor
        _RENDER_POOL = ThreadPoolExecutor(max_workers=2)
        app.state._render_pool = _RENDER_POOL
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _RENDER_POOL, render_region_tile_cached, mca_path, rx, rz, 1
    )
    if result is None:
        return JSONResponse({"error": "Failed to render region"}, status_code=500)

    if scale > 1:
        from PIL import Image
        img = Image.open(result)
        new_size = (512 * scale, 512 * scale)
        img = img.resize(new_size, Image.NEAREST)
        out = cached_region_path(rx, rz, scale)
        img.save(out)
        return FileResponse(str(out), media_type="image/png")

    return FileResponse(str(result), media_type="image/png")


@app.get("/admin/map/render/world")
async def render_world_map(request: Request, scale: int = 1):
    from map_renderer import render_world_map
    import io
    from concurrent.futures import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(ThreadPoolExecutor(), render_world_map, STORAGE_DIR, scale)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app)
