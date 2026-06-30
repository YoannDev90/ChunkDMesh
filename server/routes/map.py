"""Map generator routes: tile rendering, hover data."""

from __future__ import annotations

import io
import logging
import sys
import threading
from pathlib import Path

from config import Config
from db import Batch, get_db_session
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

logger = logging.getLogger(__name__)

_SRV = Path(__file__).resolve().parent.parent
_DATA = _SRV.parent / "data"

router = APIRouter(tags=["map"])
templates = Jinja2Templates(directory=str(_SRV / "templates"))

_map_generator = None
_map_generator_lock = threading.Lock()


def _generate_palette(map_cfg):
    """Run palette generation script if palette file is missing."""
    script = _SRV.parent / "scripts" / "generate_block_palette.py"
    if not script.exists():
        logger.warning("Palette generation script not found at %s", script)
        return
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(script), "--output", map_cfg.palette_path],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode == 0:
            with open(map_cfg.palette_path) as f:
                count = sum(1 for line in f if '"r"' in line)
            logger.info("Palette generated: %s blocks", count)
        else:
            logger.warning("Palette generation failed: %s", result.stderr[:300])
    except Exception as e:
        logger.warning("Palette generation error: %s", e)


def _init_map_generator():
    global _map_generator
    if _map_generator is not None:
        return _map_generator

    with _map_generator_lock:
        if _map_generator is not None:
            return _map_generator

        from map_generator import HoverService, MapConfig, RustTiler, TileCache
        try:
            _config = Config()
            _ = _config.world_name
        except Exception:
            pass

        map_cfg = MapConfig.from_flat_regions_dir(str(_DATA / "regions"))

        palette_path = Path(map_cfg.palette_path)
        if not palette_path.exists():
            logger.info("Block palette not found, generating from jar...")
            _generate_palette(map_cfg)

        tiler = RustTiler(
            map_cfg.rust_binary, map_cfg.palette_path,
            map_cfg.biome_colors_path, map_cfg.biome_tints_path,
        )
        cache_dir = _DATA / ".map_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = TileCache(cache_dir)
        hover = HoverService(map_cfg.region_dir, tiler, cache)

        _map_generator = {
            "config": map_cfg, "tiler": tiler, "cache": cache, "hover": hover,
        }
        return _map_generator


@router.get("/admin/map", response_class=HTMLResponse)
async def map_viewer(request: Request):
    return templates.TemplateResponse(request, "map.html")


@router.get("/admin/map/regions")
async def map_regions():
    try:
        async with get_db_session() as session:
            result = await session.execute(
                select(Batch.region_x, Batch.region_z, Batch.status)
            )
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

    if zoom == 5:
        chunk_x, chunk_z = x, y
        png = mg["cache"].get_tile_png(x, y, zoom)
        if png is None:
            region_path = mg["hover"]._get_region_path(chunk_x, chunk_z)
            if not region_path:
                raise HTTPException(status_code=404, detail="Region not found")
            png_data, _ = mg["tiler"].render_chunk(region_path, chunk_x, chunk_z)
            if png_data is None:
                raise HTTPException(status_code=500, detail="Render failed")
            mg["cache"].set_tile_png(x, y, png_data, zoom)
            png = png_data
        return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})

    try:
        from PIL import Image
    except ImportError as err:
        raise HTTPException(status_code=500, detail="Pillow required for zoom merge") from err

    async def _ensure_tile(tz: int, tx: int, ty: int) -> bytes | None:
        cached = mg["cache"].get_tile_png(tx, ty, tz)
        if cached:
            return cached
        if tz == 5:
            cx, cz = tx, ty
            rp = mg["hover"]._get_region_path(cx, cz)
            if not rp:
                return None
            png, _ = mg["tiler"].render_chunk(rp, cx, cz)
            if png:
                mg["cache"].set_tile_png(tx, ty, png, tz)
            return png
        sub = []
        for sdx in range(2):
            for sdy in range(2):
                d = await _ensure_tile(tz + 1, tx * 2 + sdx, ty * 2 + sdy)
                sub.append(d)
        im = Image.new("RGB", (128, 128))
        for idx, d in enumerate(sub):
            sdx, sdy = idx % 2, idx // 2
            if d:
                si = Image.open(io.BytesIO(d))
                im.paste(si.resize((64, 64)), (sdx * 64, sdy * 64))
            else:
                grey = Image.new("RGB", (64, 64), (40, 40, 40))
                im.paste(grey, (sdx * 64, sdy * 64))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        result = buf.getvalue()
        mg["cache"].set_tile_png(tx, ty, result, tz)
        return result

    child_tiles = []
    for dx in range(2):
        for dy in range(2):
            child = await _ensure_tile(zoom + 1, x * 2 + dx, y * 2 + dy)
            child_tiles.append((dx, dy, child))

    merged = Image.new("RGB", (128, 128))
    for dx, dy, data in child_tiles:
        if data:
            child_img = Image.open(io.BytesIO(data))
            merged.paste(child_img.resize((64, 64)), (dx * 64, dy * 64))

    buf = io.BytesIO()
    merged.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/admin/map/hover/{chunk_x}/{chunk_z}")
async def map_hover_data(chunk_x: int, chunk_z: int):
    mg = _init_map_generator()
    return JSONResponse(mg["hover"].get_hover_data(chunk_x, chunk_z))


@router.get("/admin/map/hover/{chunk_x}/{chunk_z}/{local_x}/{local_z}")
async def map_hover_pixel(chunk_x: int, chunk_z: int, local_x: int, local_z: int):
    if not (0 <= local_x < 16 and 0 <= local_z < 16):
        raise HTTPException(status_code=400, detail="Invalid local coords")
    mg = _init_map_generator()
    return JSONResponse(mg["hover"].get_block_at_pixel(chunk_x, chunk_z, local_x, local_z))
