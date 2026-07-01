"""Work loop: task fetching, generation, upload."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx


def send_request(url: str, method: str = "GET", payload=None, headers=None):
    """Send HTTP request with timeout and redirect support.

    Args:
        url: Target URL.
        method: HTTP method (GET, POST, PUT).
        payload: Optional JSON body.
        headers: Optional HTTP headers.

    Returns: httpx Response.

    Raises: ValueError for unsupported method.
    """
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        if method == "GET":
            return client.get(url, headers=headers)
        elif method == "POST":
            return client.post(url, json=payload, headers=headers)
        elif method == "PUT":
            return client.put(url, json=payload, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")


def region_dir_for_dim(server_dir: Path, dimension: str) -> Path:
    """Resolve region directory path for given dimension.

    Args:
        server_dir: Root server directory.
        dimension: Dimension name (overworld, nether, end).

    Returns: Path to region folder.
    """
    if dimension in ("nether", "the_nether", "minecraft:the_nether"):
        return server_dir / "world" / "DIM-1" / "region"
    elif dimension in ("end", "the_end", "minecraft:the_end"):
        return server_dir / "world" / "DIM1" / "region"
    return server_dir / "world" / "region"


def _count_mca_chunks(path: Path) -> int:
    try:
        with open(path, "rb") as fh:
            header = fh.read(4096)
        count = 0
        for i in range(1024):
            offset_bytes = header[i * 4 : i * 4 + 3]
            if offset_bytes != b"\x00\x00\x00":
                count += 1
        return count
    except Exception:
        return 0


def run_work_loop(
    server_url: str,
    auth_headers: dict,
    dimension: str,
    server_dir: Path,
    rcon,
    chunky,
    uploader,
    shape: str,
    monitor,
    log_fn,
    set_status_fn,
    set_region_fn,
    set_progress_fn,
    set_batch_count_fn,
    expected_chunks: int = 1024,
    tiler=None,
) -> int:
    """Main work loop. Returns batch count when done."""

    batch_count = 0
    region_dir = region_dir_for_dim(server_dir, dimension)
    region_dir.mkdir(parents=True, exist_ok=True)

    while True:
        log_fn("📦", "Fetching region task...")
        set_status_fn("fetching")
        with monitor.measure("fetch_task"):
            r = send_request(f"{server_url}/tasks/batch", headers=auth_headers)
        if r.status_code == 404:
            log_fn("📦", "No more tasks available. Done.")
            break
        if r.status_code != 200:
            log_fn("❌", f"Batch fetch failed: {r.status_code} - {r.text}")
            time.sleep(10)
            continue
        batch = r.json()
        batch_id = batch["batch_id"]
        regions = batch["regions"]
        batch_count += 1
        set_batch_count_fn(batch_count)
        if not regions:
            log_fn("⚠️", "Empty batch, skipping")
            continue

        region = regions[0]
        rx, rz = int(region["region_x"]), int(region["region_z"])
        x1, z1 = rx * 512, rz * 512
        x2, z2 = rx * 512 + 511, rz * 512 + 511
        region_label = f"({rx}, {rz})"
        set_region_fn(region_label)
        log_fn("⛏️ ", f"Batch #{batch_id}: Region {region_label} → ({x1},{z1})-({x2},{z2})")
        set_status_fn("generating", f"Region {region_label}")

        with monitor.measure("chunky_generation"):
            _run_chunky(
                chunky,
                rcon,
                x1,
                z1,
                x2,
                z2,
                shape,
                dimension,
                region_dir,
                region_label,
                log_fn,
                set_progress_fn,
                expected_chunks,
            )

        # Generate map tiles from .mca using mcmap
        if tiler:
            set_status_fn("tiling", f"Region {region_label}")
            with monitor.measure("tile_generation"):
                _generate_tiles(
                    tiler,
                    uploader,
                    region_dir,
                    rx,
                    rz,
                    region_label,
                    log_fn,
                )

        _upload_and_submit(
            server_url,
            auth_headers,
            batch_id,
            region_dir,
            rx,
            rz,
            rcon,
            uploader,
            region_label,
            expected_chunks,
            log_fn,
        )

        set_status_fn("idle", "Waiting for next task")

    return batch_count


def _run_chunky(
    chunky, rcon, x1, z1, x2, z2, shape, dimension, region_dir, region_label, log_fn, set_progress_fn, expected_chunks
):
    """Run Chunky generation for a region and poll until complete.

    Args:
        chunky: ChunkyController instance.
        rcon: RCON connection.
        x1, z1, x2, z2: Corner coordinates.
        shape: Generation shape.
        dimension: Dimension name.
        region_dir: Region output directory.
        region_label: Human-readable region label.
        log_fn: Log callback.
        set_progress_fn: Progress update callback.
        expected_chunks: Expected chunk count.
    """
    import time as _time

    from chunky_parser import parse_chunky_progress

    save_resp = rcon.run("save-all")
    log_fn("💾", f"Pre-save: {save_resp}")
    _time.sleep(3)

    sel_resp = rcon.run("chunky", "selection")
    log_fn("🔍", f"Selection: {sel_resp}")

    pre_files = list(region_dir.glob("*.mca"))
    log_fn("🔍", f"Region dir before: {len(pre_files)} files - {[f.name for f in pre_files]}")

    rcon.run("chunky", "world", "world")
    rcon.run("chunky", "dimension", dimension)
    chunky.set_corners(x1, z1, x2, z2)
    rcon.run("chunky", "shape", shape)
    rcon.run("chunky", "pattern", "loop")
    start_resp = rcon.run("chunky", "start")
    if "confirm" in start_resp.lower():
        log_fn("⛏️ ", "Existing task detected, confirming...")
        rcon.run("chunky", "confirm")
        start_resp = rcon.run("chunky", "start")
    log_fn("⛏️ ", f"Chunky: {start_resp}")

    start_t = _time.time()
    last_log = 0.0
    seen_progress = False
    last_chunks_done = 0

    while True:
        elapsed = _time.time() - start_t
        if elapsed > 1800:
            log_fn("⚠️ ", f"Region {region_label} timed out after 30min")
            chunky.cancel()
            break

        try:
            progress = chunky.status()
        except Exception as e:
            log_fn("⚠️ ", f"Progress poll failed: {e}")
            _time.sleep(5)
            continue

        set_progress_fn(progress)

        if elapsed - last_log >= 5.0:
            log_fn("⛏️ ", f"[{elapsed:.0f}s] {progress}")
            last_log = elapsed

        info = parse_chunky_progress(progress)
        last_chunks_done = info["done"]
        expected_chunks_local = min(info["total"], 1024)

        if info["done"] > 0:
            seen_progress = True

        if elapsed > 3 and (info["finished"] or "100%" in progress.lower()):
            log_fn(
                "⛏️ ",
                f"Region {region_label} done in {elapsed:.1f}s ({last_chunks_done}/{expected_chunks_local} chunks)",
            )
            break
        if seen_progress and last_chunks_done >= expected_chunks_local and expected_chunks_local > 0:
            log_fn(
                "⛏️ ",
                f"Region {region_label} done ({last_chunks_done}/{expected_chunks_local} chunks) in {elapsed:.1f}s",
            )
            break
        if info["not_running"]:
            if seen_progress:
                log_fn(
                    "⛏️ ",
                    f"Region {region_label} done in {elapsed:.1f}s ({last_chunks_done}/{expected_chunks_local} chunks)",
                )
                break
            elif elapsed > 30:
                log_fn("⚠️ ", f"Region {region_label} — no progress after {elapsed:.0f}s, assuming done")
                break
        _time.sleep(2.0)


def _upload_and_submit(
    server_url, auth_headers, batch_id, region_dir, rx, rz, rcon, uploader, region_label, expected_chunks, log_fn
):
    """Upload generated .mca files and submit hashes to server.

    Args:
        server_url: Server base URL.
        auth_headers: Authentication headers.
        batch_id: Current batch ID.
        region_dir: Region directory.
        rx, rz: Region coordinates.
        rcon: RCON connection.
        uploader: RegionUploader instance.
        region_label: Human-readable label.
        expected_chunks: Expected chunk count.
        log_fn: Log callback.
    """
    import time as _time

    log_fn("💾", "Saving world...")
    save_resp = rcon.run("save-all")
    log_fn("💾", f"save-all: {save_resp}")
    _time.sleep(3)

    sel_resp = rcon.run("chunky", "selection")
    log_fn("🔍", f"Selection after save: {sel_resp}")

    save_files = list(region_dir.glob("*.mca"))
    log_fn("🔍", f"Region dir after save: {len(save_files)} files - {[f.name for f in save_files]}")

    _time.sleep(2)
    expected_file = region_dir / f"r.{rx}.{rz}.mca"
    found = []

    for _ in range(60):
        if expected_file.exists():
            size1 = expected_file.stat().st_size
            _time.sleep(0.5)
            size2 = expected_file.stat().st_size
            if size1 == size2 and size1 > 0:
                chunk_count = _count_mca_chunks(expected_file)
                if chunk_count >= expected_chunks:
                    found.append(expected_file)
                    log_fn("💾", f"{expected_file.name}: {chunk_count}/{expected_chunks} chunks OK")
                    break
                else:
                    log_fn("⚠️ ", f"{expected_file.name}: only {chunk_count}/{expected_chunks} chunks, waiting...")
        _time.sleep(1.0)
    else:
        log_fn("⚠️ ", f"Expected {expected_file.name} not found/stable after 60s, checking all files...")
        for f in region_dir.glob("*.mca"):
            size1 = f.stat().st_size
            _time.sleep(0.5)
            size2 = f.stat().st_size
            if size1 == size2 and size1 > 0:
                found.append(f)

    rcon.run("save-off")

    try:
        all_hashes = {}
        if not found:
            log_fn("❌", f"No .mca files found for region {region_label}")
            all_files = list(region_dir.glob("*.mca"))
            log_fn("🔍", f"Files in region dir: {[f.name for f in all_files]}")
        else:
            for mca_path in found:
                file_hash = hashlib.sha256()
                with open(mca_path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 64), b""):
                        file_hash.update(chunk)
                hex_hash = file_hash.hexdigest()
                try:
                    uploader.upload_file(batch_id, mca_path)
                    log_fn("📤", f"Uploaded {mca_path.name} ({mca_path.stat().st_size} bytes)")
                    all_hashes[mca_path.name] = hex_hash
                except Exception as e:
                    log_fn("❌", f"Upload failed for {mca_path.name}: {e}")

        if all_hashes:
            log_fn("🔑", f"Submitting {len(all_hashes)} hash(es) for batch #{batch_id}...")
            try:
                submit_result = uploader.submit_hashes(batch_id, all_hashes)
                log_fn("🔑", f"Submit result: {submit_result}")
            except Exception as e:
                log_fn("❌", f"Hash submission failed: {e}")
        else:
            log_fn("⚠️", f"No files uploaded for batch #{batch_id}, skipping hash submission")
    finally:
        rcon.run("save-on")


def _generate_tiles(tiler, uploader, region_dir, rx, rz, region_label, log_fn):
    """Generate PNG tiles from .mca files using mcmap and upload to server."""

    mca_path = region_dir / f"r.{rx}.{rz}.mca"
    if not mca_path.exists():
        log_fn("⚠️", f"No .mca file for region {region_label}, skipping tile generation")
        return

    # Output dir for rendered tiles (alongside the .mca)
    tile_dir = region_dir / ".tile_output" / f"r.{rx}.{rz}"
    tile_dir.mkdir(parents=True, exist_ok=True)

    log_fn("🗺️ ", f"Rendering tiles for region {region_label}...")
    tile_paths = tiler.render_region(mca_path, tile_dir)

    if not tile_paths:
        log_fn("⚠️", f"No tiles generated for region {region_label}")
        return

    log_fn("🗺️ ", f"Generated {len(tile_paths)} tiles for region {region_label}")

    # Upload tiles to server
    log_fn("📤", f"Uploading {len(tile_paths)} tiles...")
    result = uploader.upload_tiles_batch(tile_paths, tile_dir)
    log_fn("📤", f"Uploaded {result['uploaded']} tiles, {len(result['errors'])} errors")
    if result["errors"]:
        for err in result["errors"][:3]:
            log_fn("⚠️", f"  {err}")

    # Upload hover/terrain data if available
    uploaded_hover = 0
    for stem in tile_paths:
        json_path = tile_dir / f"{stem}.json"
        terrain = tiler.parse_terrain_json(json_path)
        if terrain:
            parts = stem.split("_")
            if len(parts) == 3:
                try:
                    chunk_x = int(parts[1])
                    chunk_z = int(parts[2])
                    uploader.upload_hover_data(chunk_x, chunk_z, terrain)
                    uploaded_hover += 1
                except Exception:
                    pass
    if uploaded_hover:
        log_fn("🗺️ ", f"Uploaded {uploaded_hover} hover data files")
