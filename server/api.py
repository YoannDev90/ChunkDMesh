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
import secrets
import time as _time
from pathlib import Path
from typing import Dict, Generator, Optional

import uvicorn
import zstd
from assembler import RegionAssembler
from config import Config
from db import Batch, Client, Validation, get_db_session
from exporter import ExportManager
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from jwt import PyJWTError, decode, encode
from p2p_server import create_torrent
from pydantic import BaseModel
from s3_storage import create_storage_from_env
from sqlalchemy import select
from storage_manager import ChunkStorage, STORAGE_DIR
from tasker import attribute_tasks_to_client
logger = logging.getLogger(__name__)

_SRV = Path(__file__).resolve().parent
_ROOT = _SRV.parent
_DATA = _ROOT / "data"

app = FastAPI(
    title="ChunkDMesh Orchestrator", version="0.1.0"
)
FAVICON_PATH = _SRV / "config" / "favicon.ico"
TEMPLATES_DIR = _SRV / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    t0 = _time.monotonic()
    resp = await call_next(request)
    elapsed_ms = (_time.monotonic() - t0) * 1000
    logger.info("%s %s -> %s (%sms)", request.method, request.url.path,
                resp.status_code, f"{elapsed_ms:.0f}")
    return resp


async def run_api():
    import os
    root_logger = logging.getLogger()

    host = os.environ.get("CHUNKMESH_HOST", "0.0.0.0")
    port = int(os.environ.get("CHUNKMESH_PORT", "8000"))

    config = uvicorn.Config(
        app, host=host, port=port, log_level="info",
        log_config=None, access_log=False,
    )
    server = uvicorn.Server(config)

    # Route uvicorn loggers through our formatter
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _uvlog = logging.getLogger(name)
        _uvlog.handlers = root_logger.handlers[:]
        _uvlog.setLevel(root_logger.level)
        _uvlog.propagate = False

    await server.serve()


def get_secret_key():
    key_path = _SRV / "config" / "key.pem"
    if key_path.exists():
        return key_path.read_text().strip()
    
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
    zip_path = str(_DATA / "mods.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Mods not found")
    filename = os.path.basename(zip_path)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        file_stream_generator(zip_path), media_type="application/zip", headers=headers
    )


@app.get("/assets/config.json")
async def get_config(request: Request, token_data: dict = Depends(verify_token)):
    config = Config()
    await config.validate()
    config_dict = config.to_dict()
    return JSONResponse(config_dict)


@app.get("/tasks/batch")
async def get_batch(request: Request, token_data: dict = Depends(verify_token)):
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
    client_id = token_data.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="Invalid token payload")
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
            existing = await session.execute(
                select(Validation).where(
                    Validation.batch_id == batch_id,
                    Validation.file_hash == sha256_hash,
                )
            )
            if not existing.scalar_one_or_none():
                validation = Validation(
                    batch_id=batch_id,
                    client_id=client_id,
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
        logger.error("upload failed: batch=%s error=%s", batch_id, e)
        raise HTTPException(status_code=400, detail=str(e))


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


@app.get("/client/download")
async def download_client(request: Request):
    client_archive = _ROOT / "client" / "chunkdmesh_client.tar.gz"
    if not client_archive.exists():
        raise HTTPException(status_code=404, detail="Client archive not found")
    return FileResponse(client_archive, filename="chunkdmesh_client.tar.gz")


@app.get("/admin/stats")
async def admin_stats(request: Request):
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
    })


@app.post("/admin/assemble")
async def assemble_world(request: Request, token_data: dict = Depends(verify_token)):
    config = Config()
    assembler = RegionAssembler(config.world_name)
    result = await assembler.assemble()
    progress = assembler.get_progress()

    # Auto-cleanup: remove batch storage dirs after successful assembly
    if result.get("assembled", 0) > 0:
        storage_cleanup = ChunkStorage().cleanup_after_assembly()
        result["storage_cleanup"] = storage_cleanup

    return JSONResponse({**result, **progress})


@app.get("/admin/progress")
async def get_progress(request: Request):
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
async def export_world(request: Request, token_data: dict = Depends(verify_token)):
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
    config = Config()
    manager = ExportManager(config.world_name)
    archives = manager.list_archives()

    return JSONResponse({"archives": archives})


@app.post("/admin/torrent")
async def create_mods_torrent(request: Request, token_data: dict = Depends(verify_token)):
    zip_path = _DATA / "mods.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="mods.zip not found")

    try:
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


@app.get("/admin/progress/html")
async def get_progress_partial(request: Request):
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


if __name__ == "__main__":
    uvicorn.run(app)
