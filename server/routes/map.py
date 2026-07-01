"""Map generator routes: tile rendering, hover data."""

from __future__ import annotations

import io
import logging
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

_SRV = Path(__file__).resolve().parent.parent
_DATA = _SRV.parent / "data"

router = APIRouter(tags=["map"])
templates = Jinja2Templates(directory=str(_SRV / "templates"))

_map_generator = None
_map_generator_lock = threading.Lock()

# Overview cache: image + metadata (bounds + resolution at full scale)
_overview_cache: tuple[bytes, int, int, int, int, int, int] | None = None
# (png_data, full_w, full_h, min_chunk_x, max_chunk_x, min_chunk_z, max_chunk_z)

_overview_lock = threading.Lock()


def _init_map_generator():
    global _map_generator
    if _map_generator is not None:
        return _map_generator

    with _map_generator_lock:
        if _map_generator is not None:
            return _map_generator

        from map_generator import MapConfig, TileCache

        try:
            from config import Config

            _config = Config()
            _ = _config.world_name
        except Exception:
            pass

        map_cfg = MapConfig.from_flat_regions_dir(str(_DATA / "regions"))

        cache_dir = _DATA / ".map_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = TileCache(cache_dir)

        _map_generator = {
            "config": map_cfg,
            "cache": cache,
        }
        return _map_generator


def _build_overview_image(cache_dir: Path) -> tuple[bytes, int, int, int, int, int, int] | None:
    """Build overview from all zoom-5 tiles.

    Returns (png_data, full_w, full_h, min_cx, max_cx, min_cz, max_cz)
    where full_w/h is pixel size before downscale (used for coordinate mapping).
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    tile_files = list(cache_dir.glob("z5_x*_z*.png"))
    if not tile_files:
        return None

    tiles = []
    for f in tile_files:
        name = f.stem
        parts = name.split("_")
        try:
            tx = int(parts[1].removeprefix("x"))
            tz = int(parts[2].removeprefix("z"))
            tiles.append((tx, tz, f))
        except (IndexError, ValueError):
            continue

    if not tiles:
        return None

    sample = Image.open(tiles[0][2])
    tile_w, tile_h = sample.size
    sample.close()

    min_cx = min(t[0] for t in tiles)
    max_cx = max(t[0] for t in tiles)
    min_cz = min(t[1] for t in tiles)
    max_cz = max(t[1] for t in tiles)

    cols = max_cx - min_cx + 1
    rows = max_cz - min_cz + 1

    full_w = cols * tile_w
    full_h = rows * tile_h
    assembled = Image.new("RGB", (full_w, full_h), (34, 34, 34))

    for tx, tz, path in tiles:
        try:
            tile_img = Image.open(path)
            px = (tx - min_cx) * tile_w
            pz = (tz - min_cz) * tile_h
            assembled.paste(tile_img, (px, pz))
            tile_img.close()
        except Exception as e:
            logger.warning("Failed to read tile %s: %s", path, e)

    max_dim = 512
    if full_w > max_dim or full_h > max_dim:
        scale = min(max_dim / full_w, max_dim / full_h)
        new_w = max(1, int(full_w * scale))
        new_h = max(1, int(full_h * scale))
        assembled = assembled.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    assembled.save(buf, format="PNG", optimize=True)
    return (buf.getvalue(), full_w, full_h, min_cx, max_cx, min_cz, max_cz)


def _get_or_build_overview(cache_dir: Path) -> tuple[bytes, int, int, int, int, int, int] | None:
    """Get cached overview + metadata."""
    global _overview_cache

    if _overview_cache is not None:
        return _overview_cache

    with _overview_lock:
        if _overview_cache is not None:
            return _overview_cache

        overview_path = cache_dir / "_overview.png"
        meta_path = cache_dir / "_overview_meta.txt"

        if overview_path.exists() and meta_path.exists():
            try:
                parts = meta_path.read_text().strip().split(",")
                fw, fh, mnx, mxx, mnz, mxz = map(int, parts)
                _overview_cache = (overview_path.read_bytes(), fw, fh, mnx, mxx, mnz, mxz)
                return _overview_cache
            except Exception:
                pass

        result = _build_overview_image(cache_dir)
        if result is None:
            return None

        data, fw, fh, mnx, mxx, mnz, mxz = result
        _overview_cache = result
        try:
            overview_path.write_bytes(data)
            meta_path.write_text(f"{fw},{fh},{mnx},{mxx},{mnz},{mxz}")
        except Exception as e:
            logger.warning("Failed to write overview cache: %s", e)
        return result


def _extract_tile_from_overview(
    zoom: int, tx: int, tz: int, cache_dir: Path,
) -> bytes | None:
    """Extract a 256x256 tile for zoom < 5 from the overview image."""
    ov = _get_or_build_overview(cache_dir)
    if ov is None:
        return None

    from PIL import Image

    ov_data, full_w, full_h, min_cx, max_cx, min_cz, max_cz = ov
    ov_img = Image.open(io.BytesIO(ov_data))
    ov_w, ov_h = ov_img.size

    # Scale from overview pixels to full-resolution pixels
    scale_to_full_x = full_w / ov_w
    scale_to_full_y = full_h / ov_h

    # At zoom z, 1 tile = 2^(9-z) blocks = 2^(5-z) chunks
    chunks_per_tile = 1 << (5 - zoom)
    blocks_per_tile = chunks_per_tile * 16

    # Tile (tx, tz) covers blocks [tx * blocks_per_tile, (tx+1) * blocks_per_tile) in X, same for Z
    block_start_x = tx * blocks_per_tile
    block_start_z = tz * blocks_per_tile

    # Full-res pixel for block (bx, bz):
    # pix_x = (bx - min_cx * 16) * (full_w / ((max_cx - min_cx + 1) * 16))
    # But full_w = (max_cx - min_cx + 1) * 256, so full_w / chunks = 256
    # And 256 px / 16 blocks = 16 px per block
    # pix_x = (bx - min_cx * 16) * 16
    pix_start_x = (block_start_x - min_cx * 16) * 16
    pix_start_z = (block_start_z - min_cz * 16) * 16
    pix_size = blocks_per_tile * 16  # pixels at full res

    # Map to overview pixels
    ov_px_start_x = pix_start_x / scale_to_full_x
    ov_px_start_z = pix_start_z / scale_to_full_y
    ov_px_size = pix_size / scale_to_full_x  # same for y since aspect ratio preserved

    # Clamp to overview bounds
    ov_px_start_x = max(0.0, min(ov_w - 1.0, ov_px_start_x))
    ov_px_start_z = max(0.0, min(ov_h - 1.0, ov_px_start_z))
    ov_px_end_x = min(ov_w, ov_px_start_x + ov_px_size)
    ov_px_end_z = min(ov_h, ov_px_start_z + ov_px_size)

    if ov_px_end_x - ov_px_start_x < 1 or ov_px_end_z - ov_px_start_z < 1:
        ov_img.close()
        return None

    region = ov_img.crop((ov_px_start_x, ov_px_start_z, ov_px_end_x, ov_px_end_z))
    region = region.resize((256, 256), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    region.save(buf, format="PNG", optimize=True)
    region.close()
    ov_img.close()
    return buf.getvalue()


def invalidate_overview():
    """Call when new tiles are uploaded to force overview rebuild."""
    global _overview_cache
    _overview_cache = None
    overview_path = _DATA / ".map_cache" / "_overview.png"
    if overview_path.exists():
        overview_path.unlink(missing_ok=True)
    meta_path = _DATA / ".map_cache" / "_overview_meta.txt"
    if meta_path.exists():
        meta_path.unlink(missing_ok=True)


@router.get("/admin/map", response_class=HTMLResponse)
async def map_viewer(request: Request):
    return templates.TemplateResponse(request, "map.html")


@router.get("/admin/map/regions")
async def map_regions():
    from db import Batch, get_db_session
    from sqlalchemy import select

    try:
        async with get_db_session() as session:
            result = await session.execute(select(Batch.region_x, Batch.region_z, Batch.status))
            rows = result.all()
        regions = [{"region_x": r.region_x, "region_z": r.region_z, "status": r.status} for r in rows]
    except Exception:
        regions = []
    return JSONResponse({"regions": regions})


@router.get("/admin/map/tile/{zoom}/{x}/{y}.png")
async def map_tile(zoom: int, x: int, y: int):
    if zoom < 0 or zoom > 5:
        raise HTTPException(status_code=400, detail="Invalid zoom")

    mg = _init_map_generator()
    cache_dir = Path(mg["config"].tile_cache_dir)

    # Zoom 5: serve directly from cache
    if zoom == 5:
        png = mg["cache"].get_tile_png(x, y)
        if png is None:
            raise HTTPException(status_code=404, detail="Tile not found (client must generate)")
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})

    # Zoom 0-4: extract correct sub-region from overview
    tile_png = _extract_tile_from_overview(zoom, x, y, cache_dir)
    if tile_png is None:
        raise HTTPException(status_code=404, detail="No tiles available for overview")
    return Response(content=tile_png, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})


@router.get("/admin/map/hover/{chunk_x}/{chunk_z}")
async def map_hover_data(chunk_x: int, chunk_z: int):
    mg = _init_map_generator()
    cached = mg["cache"].get_hover_data(chunk_x, chunk_z)
    if cached:
        return JSONResponse(cached)
    raise HTTPException(status_code=404, detail="Hover data not found (client must generate)")


@router.get("/admin/map/hover/{chunk_x}/{chunk_z}/{local_x}/{local_z}")
async def map_hover_pixel(chunk_x: int, chunk_z: int, local_x: int, local_z: int):
    if not (0 <= local_x < 16 and 0 <= local_z < 16):
        raise HTTPException(status_code=400, detail="Invalid local coords")
    mg = _init_map_generator()
    cached = mg["cache"].get_hover_data(chunk_x, chunk_z)
    if not cached:
        raise HTTPException(status_code=404, detail="Hover data not found (client must generate)")
    return JSONResponse(cached)
