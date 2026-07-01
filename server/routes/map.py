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

# Pre-generated overview image (zoom 0-4 all return this)
_overview_cache: bytes | None = None
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


def _build_overview_image(cache_dir: Path) -> bytes | None:
    """Build a single overview PNG from all zoom-5 tiles.

    Finds the bounding box of all tiles, assembles them into one image,
    then downscales to 512x512 (or smaller). Returns PNG bytes.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    tile_files = list(cache_dir.glob("z5_x*_z*.png"))
    if not tile_files:
        return None

    # Parse tile coords
    tiles = []
    for f in tile_files:
        name = f.stem  # z5_x123_z456
        parts = name.split("_")
        try:
            tx = int(parts[1].removeprefix("x"))
            tz = int(parts[2].removeprefix("z"))
            tiles.append((tx, tz, f))
        except (IndexError, ValueError):
            continue

    if not tiles:
        return None

    # Determine tile size from first tile
    sample = Image.open(tiles[0][2])
    tile_w, tile_h = sample.size
    sample.close()

    # Bounding box
    min_x = min(t[0] for t in tiles)
    max_x = max(t[0] for t in tiles)
    min_z = min(t[1] for t in tiles)
    max_z = max(t[1] for t in tiles)

    cols = max_x - min_x + 1
    rows = max_z - min_z + 1

    # Cap overview size: if too many tiles, downscale more
    max_dim = 512
    scale = min(1.0, max_dim / (cols * tile_w), max_dim / (rows * tile_h))
    out_w = int(cols * tile_w * scale)
    out_h = int(rows * tile_h * scale)

    overview = Image.new("RGB", (out_w, out_h), (34, 34, 34))

    for tx, tz, path in tiles:
        try:
            tile_img = Image.open(path)
            # Position in overview
            px = int((tx - min_x) * tile_w * scale)
            pz = int((tz - min_z) * tile_h * scale)
            tw = max(1, int(tile_w * scale))
            th = max(1, int(tile_h * scale))
            overview.paste(tile_img.resize((tw, th), Image.Resampling.LANCZOS), (px, pz))
            tile_img.close()
        except Exception as e:
            logger.warning("Failed to read tile %s: %s", path, e)

    buf = io.BytesIO()
    overview.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _get_or_build_overview(cache_dir: Path) -> bytes | None:
    """Get cached overview or build it."""
    global _overview_cache

    if _overview_cache is not None:
        return _overview_cache

    with _overview_lock:
        if _overview_cache is not None:
            return _overview_cache

        overview_path = cache_dir / "_overview.png"
        if overview_path.exists():
            _overview_cache = overview_path.read_bytes()
            return _overview_cache

        data = _build_overview_image(cache_dir)
        if data is None:
            return None

        _overview_cache = data
        try:
            overview_path.write_bytes(data)
        except Exception as e:
            logger.warning("Failed to write overview cache: %s", e)
        return data


def invalidate_overview():
    """Call when new tiles are uploaded to force overview rebuild."""
    global _overview_cache
    _overview_cache = None
    overview_path = _DATA / ".map_cache" / "_overview.png"
    if overview_path.exists():
        overview_path.unlink(missing_ok=True)


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

    # Zoom 0-4: serve the single overview image
    overview = _get_or_build_overview(cache_dir)
    if overview is None:
        raise HTTPException(status_code=404, detail="No tiles available for overview")
    return Response(content=overview, media_type="image/png", headers={"Cache-Control": "public, max-age=600"})


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
