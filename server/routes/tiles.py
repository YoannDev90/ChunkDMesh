"""Tile routes: upload pre-rendered PNGs, serve palette files."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import zstd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from routes.auth import verify_token

logger = logging.getLogger(__name__)

_SRV = Path(__file__).resolve().parent.parent
_DATA = _SRV.parent / "data"

router = APIRouter(prefix="/tiles", tags=["tiles"])


@router.put("/upload")
async def upload_tile(request: Request, token_data: dict = Depends(verify_token)):
    """Receive a pre-rendered PNG tile from a client."""
    chunk_x = request.headers.get("X-Chunk-X")
    chunk_z = request.headers.get("X-Chunk-Z")
    if chunk_x is None or chunk_z is None:
        raise HTTPException(status_code=400, detail="Missing X-Chunk-X or X-Chunk-Z header")

    try:
        chunk_x = int(chunk_x)
        chunk_z = int(chunk_z)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid chunk coords") from err

    body = await request.body()
    try:
        png_data = zstd.decompress(body)
    except Exception:
        png_data = body  # Accept uncompressed

    # Store in tile cache
    from map_generator import MapConfig

    map_cfg = MapConfig.from_flat_regions_dir(str(_DATA / "regions"))
    cache_dir = Path(map_cfg.tile_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    tile_path = cache_dir / f"z5_x{chunk_x}_z{chunk_z}.png"
    tile_path.write_bytes(png_data)

    logger.info("Tile uploaded: chunk_%d_%d (%d bytes)", chunk_x, chunk_z, len(png_data))
    return JSONResponse({"status": "ok", "chunk_x": chunk_x, "chunk_z": chunk_z, "size": len(png_data)})


@router.put("/hover/{chunk_x}/{chunk_z}")
async def upload_hover(chunk_x: int, chunk_z: int, request: Request, token_data: dict = Depends(verify_token)):
    """Receive hover/terrain JSON data for a chunk."""
    body = await request.body()
    try:
        terrain = json.loads(body)
    except json.JSONDecodeError as err:
        raise HTTPException(status_code=400, detail="Invalid JSON") from err

    from map_generator import MapConfig

    map_cfg = MapConfig.from_flat_regions_dir(str(_DATA / "regions"))
    cache_dir = Path(map_cfg.tile_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    hover_path = cache_dir / f"hover_{chunk_x}_{chunk_z}.json"
    hover_path.write_text(json.dumps(terrain))

    logger.info("Hover data uploaded: chunk_%d_%d", chunk_x, chunk_z)
    return JSONResponse({"status": "ok", "chunk_x": chunk_x, "chunk_z": chunk_z})


@router.get("/palette/{filename}")
async def serve_palette(filename: str):
    """Serve palette files to clients for local mcmap rendering."""
    allowed = {"block_colors.json", "biome_colors.json", "biome_tint_blocks.json"}
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="File not found")

    path = _DATA / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Palette not generated yet")

    return FileResponse(path, media_type="application/json")


@router.get("/palette")
async def list_palettes():
    """List available palette files."""
    files = []
    for name in ["block_colors.json", "biome_colors.json", "biome_tint_blocks.json"]:
        path = _DATA / name
        files.append({"name": name, "exists": path.exists(), "size": path.stat().st_size if path.exists() else 0})
    return JSONResponse({"palettes": files})
