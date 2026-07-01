"""Admin routes: dashboard, stats, export, heatmap, torrent."""

from __future__ import annotations

import logging
from pathlib import Path

from assembler import RegionAssembler
from config import Config
from constants import sanitize_filename
from db import Batch, get_db_session
from exporter import ExportManager
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from p2p_server import create_torrent
from routes.auth import verify_token
from s3_storage import create_storage_from_env
from sqlalchemy import select
from storage_manager import ChunkStorage

logger = logging.getLogger(__name__)

_SRV = Path(__file__).resolve().parent.parent
_DATA = _SRV.parent / "data"
ROOT = _SRV.parent

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(_SRV / "templates"))


@router.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve admin dashboard HTML."""
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/admin/heatmap")
async def get_heatmap(request: Request):
    """Return region batch status data as JSON for heatmap."""
    async with get_db_session() as session:
        result = await session.execute(select(Batch.region_x, Batch.region_z, Batch.status, Batch.assigned_to))
        rows = result.all()
    return JSONResponse(
        {
            "regions": [
                {"region_x": r.region_x, "region_z": r.region_z, "status": r.status, "assigned_to": r.assigned_to}
                for r in rows
            ]
        }
    )


@router.get("/admin/heatmap/html")
async def get_heatmap_partial(request: Request):
    """Return HTML partial for heatmap grid."""
    async with get_db_session() as session:
        result = await session.execute(select(Batch.region_x, Batch.region_z, Batch.status))
        rows = result.all()

    if not rows:
        return templates.TemplateResponse(request, "heatmap_partial.html", {"regions": [], "cols": 1})

    min_x = min(r.region_x for r in rows)
    max_x = max(r.region_x for r in rows)
    min_z = min(r.region_z for r in rows)
    max_z = max(r.region_z for r in rows)

    grid = {(r.region_x, r.region_z): r.status for r in rows}
    regions = [
        {"region_x": x, "region_z": z, "status": grid.get((x, z), "pending")}
        for z in range(min_z, max_z + 1)
        for x in range(min_x, max_x + 1)
    ]

    return templates.TemplateResponse(
        request,
        "heatmap_partial.html",
        {
            "regions": regions,
            "cols": max_x - min_x + 1,
        },
    )


@router.get("/admin/stats")
async def admin_stats(request: Request):
    """Return storage and batch statistics."""
    storage = ChunkStorage()
    regions = storage.list_regions()

    blob_dir = storage.regions_dir / ".blobs"
    blob_count = 0
    blob_size_mb = 0.0
    if blob_dir.exists():
        blob_files = list(blob_dir.iterdir())
        blob_count = len(blob_files)
        blob_size_mb = round(sum(f.stat().st_size for f in blob_files) / (1024 * 1024), 1)

    async with get_db_session() as session:
        status_result = await session.execute(select(Batch.status))
        statuses = status_result.scalars().all()

    status_counts: dict[str, int] = {}
    for s in statuses:
        status_counts[s] = status_counts.get(s, 0) + 1

    return JSONResponse(
        {
            "storage": {
                "region_files": len(regions),
                "blobs": blob_count,
                "blobs_size_mb": blob_size_mb,
                "total_size_mb": storage.total_size_mb(),
            },
            "database": {
                "total_batches": len(statuses),
                "by_status": status_counts,
            },
        }
    )


@router.get("/admin/progress")
async def get_progress(request: Request):
    """Return assembly progress and batch status counts."""
    config = Config()
    assembler = RegionAssembler(config.world_name)
    progress = assembler.get_progress()

    async with get_db_session() as session:
        batch_result = await session.execute(select(Batch.status))
        statuses = batch_result.scalars().all()

    status_counts: dict[str, int] = {}
    for s in statuses:
        status_counts[s] = status_counts.get(s, 0) + 1

    return JSONResponse({"files": progress, "batches": status_counts})


@router.get("/admin/progress/html")
async def get_progress_partial(request: Request):
    """Return HTML partial for progress stats."""
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

    return templates.TemplateResponse(
        request,
        "stats_partial.html",
        {
            "total_files": progress["total_files"],
            "total_size_mb": progress["total_size_mb"],
            **counts,
        },
    )


@router.post("/admin/assemble")
async def assemble_world(request: Request):
    """Trigger region assembly from flat storage to export dir."""
    config = Config()
    assembler = RegionAssembler(config.world_name)
    result = await assembler.assemble()
    return JSONResponse({**result, **assembler.get_progress()})


@router.post("/admin/export")
async def export_world(request: Request, token_data: dict = Depends(verify_token)):
    """Create .tar.gz archive of assembled world."""
    config = Config()
    manager = ExportManager(config.world_name)
    try:
        archive_path = manager.export()
        return JSONResponse(
            {
                "status": "exported",
                "archive": archive_path.name,
                "download": f"/admin/download/{archive_path.name}",
            }
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/admin/archives")
async def list_archives(request: Request):
    """List available export archives."""
    config = Config()
    manager = ExportManager(config.world_name)
    return JSONResponse({"archives": manager.list_archives()})


@router.post("/admin/torrent")
async def create_mods_torrent(request: Request, token_data: dict = Depends(verify_token)):
    """Create .torrent file for P2P mods.zip distribution."""
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
        return JSONResponse({"status": "created", "torrent": torrent_path.name, "download_url": download_url})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/admin/download/{filename}")
async def download_archive(filename: str, request: Request, token_data: dict = Depends(verify_token)):
    """Download an export archive with path traversal protection."""
    try:
        safe_name = sanitize_filename(filename)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid filename") from err
    config = Config()
    manager = ExportManager(config.world_name)
    archive_path = (manager.exports_dir / safe_name).resolve()
    exports_dir = manager.exports_dir.resolve()
    if not str(archive_path).startswith(str(exports_dir)):
        raise HTTPException(status_code=400, detail="Path traversal detected")
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Archive not found")
    return FileResponse(archive_path, media_type="application/gzip", filename=safe_name)


@router.get("/client/download")
async def download_client(request: Request):
    """Download client archive for distribution."""
    client_archive = ROOT / "client" / "chunkdmesh_client.tar.gz"
    if not client_archive.exists():
        raise HTTPException(status_code=404, detail="Client archive not found")
    return FileResponse(client_archive, filename="chunkdmesh_client.tar.gz")


@router.get("/admin/logs")
async def get_logs():
    """Return recent log entries for dashboard."""
    from state import server_state

    logs = server_state.recent_logs()
    return JSONResponse({"logs": [{"ts": ts, "icon": icon, "msg": msg} for ts, icon, msg in logs]})


@router.get("/admin/requests")
async def get_requests():
    """Return recent API requests for dashboard."""
    from state import server_state

    recent = server_state.recent_requests()
    return JSONResponse({"requests": [{"ts": ts, "path": path, "status": status} for ts, path, status in recent[-50:]]})


@router.get("/admin/project")
async def get_project():
    """Return project info: uptime, config, task counts, clients."""
    import time as _time

    from state import server_state

    stats = server_state.snapshot()
    uptime = _time.time() - stats.start_time
    h, rem = divmod(int(uptime), 3600)
    m, s = divmod(rem, 60)

    return JSONResponse(
        {
            "uptime": f"{h:02d}:{m:02d}:{s:02d}",
            "config": stats.world_config,
            "clients": stats.active_clients,
            "tasks": {
                "pending": stats.pending_tasks,
                "assigned": stats.assigned_tasks,
                "working": stats.working_tasks,
                "completed": stats.completed_tasks,
                "validated": stats.validated_tasks,
            },
            "request_count": stats.request_count,
            "total_storage_mb": stats.total_storage_mb,
        }
    )
