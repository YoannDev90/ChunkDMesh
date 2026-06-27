import io
import subprocess
from pathlib import Path

from PIL import Image

STORAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "storage"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "map_cache"
TILER_PATH = Path(__file__).resolve().parent.parent / "bin" / "chunkdmesh-tiler"

_HAS_RUST_TILER = TILER_PATH.exists()


# ── Renderer — Rust tiler only ──────────────────────────────────────────────


def render_region_tile(
    mca_path: Path, region_rx: int, region_rz: int, scale: int = 1
) -> Image.Image | None:
    if not _HAS_RUST_TILER:
        return None

    try:
        result = subprocess.run(
            [str(TILER_PATH), "render", "--input", str(mca_path), "--scale", str(scale)],
            capture_output=True, timeout=30,
        )
        if result.returncode == 0:
            img = Image.open(io.BytesIO(result.stdout))
            img.load()
            return img.convert("RGB")
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        pass

    return None


def cached_region_path(rx: int, rz: int, scale: int, ext: str = "png") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"r.{rx}.{rz}.s{scale}.{ext}"


def render_region_tile_cached(
    mca_path: Path, region_rx: int, region_rz: int, scale: int = 1,
) -> Path | None:
    img = render_region_tile(mca_path, region_rx, region_rz, scale)
    if img is None:
        return None

    out = cached_region_path(region_rx, region_rz, scale)
    img.save(out, format="PNG", optimize=True)
    return out


def render_world_map(
    storage_dir: Path = STORAGE_DIR,
    scale: int = 1,
) -> Image.Image:
    batch_dirs = sorted(
        [d for d in storage_dir.iterdir() if d.is_dir() and d.name.isdigit()],
        key=lambda p: int(p.name),
    )

    if not batch_dirs:
        return Image.new("RGB", (512, 512), (30, 30, 30))

    tile_map: dict[tuple[int, int], Path] = {}
    for bdir in batch_dirs:
        for mca in bdir.glob("r.*.*.mca"):
            parts = mca.stem.split(".")
            if len(parts) != 3:
                continue
            rx, rz = int(parts[1]), int(parts[2])
            if (rx, rz) not in tile_map:
                tile_map[(rx, rz)] = mca

    if not tile_map:
        return Image.new("RGB", (512, 512), (30, 30, 30))

    min_rx = min(k[0] for k in tile_map)
    max_rx = max(k[0] for k in tile_map)
    min_rz = min(k[1] for k in tile_map)
    max_rz = max(k[1] for k in tile_map)

    tile_size = 512 * scale
    w = (max_rx - min_rx + 1) * tile_size
    h = (max_rz - min_rz + 1) * tile_size
    world = Image.new("RGB", (w, h), (30, 30, 30))

    for (rx, rz), mca_path in tile_map.items():
        img = render_region_tile(mca_path, rx, rz, scale)
        if img:
            ox = (rx - min_rx) * tile_size
            oy = (rz - min_rz) * tile_size
            world.paste(img, (ox, oy))

    return world
