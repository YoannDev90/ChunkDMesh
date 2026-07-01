"""Tile routes: upload pre-rendered PNGs, serve palette files."""

from __future__ import annotations

import json
import logging
import struct
import subprocess
import sys
from pathlib import Path

import zstd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from routes.auth import verify_token

logger = logging.getLogger(__name__)

_SRV = Path(__file__).resolve().parent.parent
_DATA = _SRV.parent / "data"

router = APIRouter(prefix="/tiles", tags=["tiles"])

_ZSTD_MAX_RATIO = 16


def _safe_decompress(body: bytes, max_decompressed: int) -> bytes:
    """Decompress zstd data with ratio-based OOM guard.

    Rejects if compressed_size * max_ratio > max_decompressed.

    Args:
        body: Raw request body (zstd-compressed or raw).
        max_decompressed: Max allowed decompressed size in bytes.

    Returns: Decompressed data.
    """
    try:
        est = len(body) * _ZSTD_MAX_RATIO
        if est > max_decompressed:
            raise HTTPException(
                status_code=413,
                detail=f"Payload too large: {len(body)} compressed would decompress to >{max_decompressed} bytes",
            )
        return zstd.decompress(body)
    except HTTPException:
        raise
    except Exception:
        return body


def _ensure_palettes() -> bool:
    """Generate palette files if they don't exist. Returns True if all present."""
    required = ["block_colors.json", "biome_colors.json", "biome_tint_blocks.json"]
    if all((_DATA / f).exists() for f in required):
        return True

    script = _SRV.parent / "scripts" / "generate_block_palette.py"
    if not script.exists():
        logger.warning("Palette generation script not found at %s", script)
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("Palettes generated automatically")
            return True
        logger.warning("Palette generation failed: %s", result.stderr[-300:])
    except Exception as e:
        logger.warning("Palette generation error: %s", e)
    return False


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
    png_data = _safe_decompress(body, max_decompressed=10 * 1024 * 1024)

    # Store in tile cache
    from map_generator import MapConfig

    map_cfg = MapConfig.from_flat_regions_dir(str(_DATA / "regions"))
    cache_dir = Path(map_cfg.tile_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    tile_path = cache_dir / f"z5_x{chunk_x}_z{chunk_z}.png"
    tile_path.write_bytes(png_data)

    # Invalidate overview so it gets rebuilt with new tiles
    from routes.map import invalidate_overview

    invalidate_overview()

    logger.info("Tile uploaded: chunk_%d_%d (%d bytes)", chunk_x, chunk_z, len(png_data))
    return JSONResponse({"status": "ok", "chunk_x": chunk_x, "chunk_z": chunk_z, "size": len(png_data)})


@router.put("/upload/batch")
async def upload_tiles_batch(request: Request, token_data: dict = Depends(verify_token)):
    """Receive multiple pre-rendered PNG tiles in one request.

    Format: zstd-compressed binary with repeated 12-byte header + PNG data:
      chunk_x: i32 (4 bytes, little-endian)
      chunk_z: i32 (4 bytes, little-endian)
      size:    u32 (4 bytes, little-endian)
      png_data: size bytes
    """
    body = await request.body()
    data = _safe_decompress(body, max_decompressed=500 * 1024 * 1024)

    from map_generator import MapConfig

    map_cfg = MapConfig.from_flat_regions_dir(str(_DATA / "regions"))
    cache_dir = Path(map_cfg.tile_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    offset = 0
    count = 0
    while offset + 12 <= len(data):
        chunk_x = struct.unpack_from("<i", data, offset)[0]
        chunk_z = struct.unpack_from("<i", data, offset + 4)[0]
        size = struct.unpack_from("<I", data, offset + 8)[0]
        offset += 12
        if offset + size > len(data):
            break
        png_data = data[offset : offset + size]
        offset += size

        tile_path = cache_dir / f"z5_x{chunk_x}_z{chunk_z}.png"
        tile_path.write_bytes(png_data)
        count += 1

    # Invalidate overview once for the whole batch
    from routes.map import invalidate_overview

    invalidate_overview()

    logger.info("Batch upload: %d tiles (%d bytes compressed)", count, len(body))
    return JSONResponse({"status": "ok", "count": count, "bytes": len(body)})


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
        _ensure_palettes()

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
