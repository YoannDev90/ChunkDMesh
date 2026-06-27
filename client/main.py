"""ChunkDMesh Client - Worker that connects to the orchestrator and generates chunks."""

import sys
import threading
import time
from pathlib import Path

_client_dir = str(Path(__file__).resolve().parent)
if _client_dir not in sys.path:
    sys.path.insert(0, _client_dir)
_project_dir = str(Path(__file__).resolve().parent.parent)
_server_dir = str(Path(__file__).resolve().parent.parent / "server")
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)

import httpx
from api_config import SERVER_URL
from utils import ResourceReportFormat, get_available_resources_averaged


def log(icon: str, msg: str):
    print(f"  {icon} {msg}")


def wait_for_server(url: str, max_wait: float = 120.0) -> bool:
    delay = 0.5
    start = time.time()
    log("⏳", f"Waiting for server at {url}...")
    while time.time() - start < max_wait:
        try:
            with httpx.Client(timeout=3) as client:
                resp = client.get(f"{url}/health")
                if resp.status_code == 200:
                    log("✅", "Server is up")
                    return True
        except (httpx.ConnectError, httpx.ReadTimeout, ConnectionRefusedError):
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 5.0)
    return False


def send_request(url: str, method: str = "GET", payload=None, headers=None):
    with httpx.Client(timeout=120) as client:
        if method == "GET":
            return client.get(url, headers=headers)
        elif method == "POST":
            return client.post(url, json=payload, headers=headers)
        elif method == "PUT":
            return client.put(url, json=payload, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")


def region_dir_for_dim(server_dir: Path, dimension: str) -> Path:
    if dimension in ("nether", "the_nether", "minecraft:the_nether"):
        return server_dir / "world" / "DIM-1" / "region"
    elif dimension in ("end", "the_end", "minecraft:the_end"):
        return server_dir / "world" / "DIM1" / "region"
    return server_dir / "world" / "region"


def main():
    print("=" * 50)
    print("  ChunkDMesh Client")
    print("=" * 50)
    print()

    if not wait_for_server(SERVER_URL):
        log("❌", "Server unreachable after 120s, aborting.")
        return

    # ── Power score ─────────────────────────────────────────
    print()
    log("📊", "Power score...")
    power_score = get_available_resources_averaged(
        print_output=False, return_format=ResourceReportFormat.VALUE
    )
    log("📊", f"Score: {power_score:.2f}")

    # ── Login ──────────────────────────────────────────────
    print()
    log("🔑", "Logging in...")
    r = send_request(
        f"{SERVER_URL}/auth/login",
        method="POST",
        payload={"power_score": power_score},
    )
    if r.status_code != 200:
        log("❌", f"Login failed: {r.status_code} - {r.text}")
        return
    token = r.json()["token"]
    log("🔑", f"Token acquired")

    auth_headers = {"Authorization": f"Bearer {token}"}

    # ── Fetch config ────────────────────────────────────────
    print()
    log("⚙️ ", "Fetching config...")
    r = send_request(f"{SERVER_URL}/assets/config.json", headers=auth_headers)
    if r.status_code != 200:
        log("❌", f"Config fetch failed: {r.status_code} - {r.text}")
        return
    config = r.json()
    mc_version = config.get("minecraft_version", "1.20.4")
    loader = config.get("minecraft_loader", "fabric")
    loader_version = config.get("loader_version", "0.19.3")
    seed = config.get("seed", 0)
    radius = config.get("radius", 1024)
    shape = config.get("shape", "square")
    dimension = config.get("dimension", "overworld")
    log("⚙️ ", f"MC {mc_version} / {loader} {loader_version}")
    log("⚙️ ", f"Seed: {seed} / Radius: {radius} / Shape: {shape} / Dim: {dimension}")

    # ── Java ────────────────────────────────────────────────
    print()
    log("☕", "Detecting Java...")
    from java_utils import ensure_java
    try:
        java_home = ensure_java(mc_version)
        java_bin = java_home / "bin" / "java"
        log("☕", f"Java ready: {java_home}")
    except Exception as e:
        log("❌", f"Java detection failed: {e}")
        return

    # ── Setup server dir + install loader ─────────────────────
    print()
    log("📁", "Setting up server...")
    from asset_manager import AssetManager

    work_dir = Path.home() / ".chunkdmesh" / "work"
    asset_mgr = AssetManager(SERVER_URL, token, work_dir=work_dir)

    server_dir = asset_mgr.setup_server_dir(mc_version, loader, loader_version)
    log("📁", f"Server dir: {server_dir}")

    # ── Download mods (server mods.zip OR Modrinth) ──────────
    print()
    log("📥", "Downloading mods...")
    if config.get("has_mods_zip"):
        mods_zip = asset_mgr.download_mods()
        log("📥", f"Mods downloaded: {mods_zip}")
        print()
        log("🧩", "Extracting mods...")
        mods_dir = asset_mgr.extract_mods(mods_zip)
        log("🧩", f"Mods extracted to: {mods_dir}")
    else:
        log("📥", "No mods.zip configured, downloading Chunky + deps from Modrinth...")
        from modrinth import get_modrinth_download, CHUNKY_MODRINTH_PROJECT_ID, FABRIC_API_PROJECT_ID

        chunky_ver = config.get("chunky_version", "")
        chunky_info = get_modrinth_download(CHUNKY_MODRINTH_PROJECT_ID, chunky_ver, loader, mc_version)
        if not chunky_info:
            log("❌", "Could not find Chunky version on Modrinth")
            return
        asset_mgr.download_from_modrinth(CHUNKY_MODRINTH_PROJECT_ID, chunky_ver, mc_version, loader)

        fabric_api_info = get_modrinth_download(FABRIC_API_PROJECT_ID, "", "fabric", mc_version)
        if fabric_api_info:
            asset_mgr.download_from_modrinth(FABRIC_API_PROJECT_ID, "", mc_version, "fabric")
            log("📥", "Fabric API downloaded")
        else:
            log("⚠️", "Fabric API not found, continuing without it")

    print()
    log("🔧", f"Installing {loader} {loader_version}...")
    try:
        jar_path = asset_mgr.get_server_jar(mc_version, loader, loader_version)
        log("🔧", f"Server jar: {jar_path}")
    except Exception as e:
        log("❌", f"Loader install failed: {e}")
        return

    # ── Launch MC + RCON ────────────────────────────────────
    print()
    log("🚀", "Launching server...")
    from instance_runner import MCServer

    asset_mgr.write_server_properties(seed=seed)
    log("🚀", f"server.properties written (seed={seed}, RCON enabled)")

    server = MCServer(
        server_dir=server_dir,
        java_bin=java_bin,
        jar_path=jar_path,
        xmx_mb=4096,
        xms_mb=1024,
    )

    server.start()
    log("🚀", f"Server process PID: {server.get_pid()}")

    mc_log_path = server_dir / "logs" / "latest.log"
    mc_log_pos = mc_log_path.stat().st_size if mc_log_path.exists() else 0
    mc_log_stop = threading.Event()

    def _stream_mc_logs():
        nonlocal mc_log_pos
        import time as _t
        import re as _re
        while not mc_log_stop.is_set():
            try:
                if mc_log_path.exists():
                    with open(mc_log_path, "r") as f:
                        f.seek(mc_log_pos)
                        new_lines = f.readlines()
                        mc_log_pos = f.tell()
                        for line in new_lines:
                            line = line.rstrip()
                            if not line:
                                continue
                            # Strip MC metadata [HH:MM:SS] [Thread/LEVEL]:
                            msg = _re.sub(r'^\[\d{2}:\d{2}:\d{2}\]\s*\[[^\]]+\]\s*:\s*', '', line)
                            log("📜", msg)
            except Exception:
                pass
            _t.sleep(1.0)

    mc_log_thread = threading.Thread(target=_stream_mc_logs, daemon=True)
    mc_log_thread.start()

    if not server.wait_until_ready(timeout=300):
        log("❌", "Server failed to start within 300s")
        mc_log_stop.set()
        server.stop()
        return

    rcon_props_path = server_dir / "server.properties"
    rcon_enabled = False
    if rcon_props_path.exists():
        with open(rcon_props_path) as f:
            rcon_enabled = "enable-rcon=true" in f.read()

    if not rcon_enabled:
        log("🚀", "RCON not in server.properties, rewriting and restarting...")
        mc_log_stop.set()
        server.stop()
        mc_log_pos = mc_log_path.stat().st_size if mc_log_path.exists() else 0
        mc_log_stop.clear()
        asset_mgr.write_server_properties()
        server = MCServer(
            server_dir=server_dir,
            java_bin=java_bin,
            jar_path=jar_path,
            xmx_mb=4096,
            xms_mb=1024,
        )
        server.start()
        mc_log_thread = threading.Thread(target=_stream_mc_logs, daemon=True)
        mc_log_thread.start()
        if not server.wait_until_ready(timeout=300):
            log("❌", "Server failed to restart with RCON")
            mc_log_stop.set()
            server.stop()
            return

    log("🚀", "Server is ready!")

    print()
    log("🔗", "Connecting RCON...")
    from rcon_client import RCONConnection, ChunkyController

    rcon = RCONConnection(host="127.0.0.1", port=25575, password="chunkdmesh")
    if not rcon.connect(retries=15, delay=2.0):
        log("❌", "RCON connection failed")
        server.stop()
        return
    log("🔗", "RCON connected")

    chunky = ChunkyController(rcon)

    # ── Texture atlas init (client jar + mod jars) ──────────────────────
    print()
    log("🖼️", "Building texture atlas from client jar + mods...")
    try:
        from server.texture_extractor import build_texture_atlas
        tex_dir = Path.home() / ".chunkdmesh" / "textures"
        tex_dir.mkdir(parents=True, exist_ok=True)
        mod_jar_dir = work_dir / "server" / "mods"
        mod_jars = list(mod_jar_dir.glob("*.jar")) if mod_jar_dir.exists() else []
        texture_atlas = build_texture_atlas(mc_version, tex_dir, mod_jars)
        log("🖼️", f"Atlas ready: {len(texture_atlas.block_texture)} blocks mapped")
    except Exception as e:
        log("⚠️", f"Texture atlas init failed ({e}), falling back to solid colors")
        texture_atlas = None

    # ── Work loop: fetch single region → generate → save → upload → repeat ──
    import time as _time
    from uploader import RegionUploader
    import hashlib
    uploader = RegionUploader(SERVER_URL, token)
    batch_count = 0

    region_dir = region_dir_for_dim(server_dir, dimension)
    region_dir.mkdir(parents=True, exist_ok=True)

    while True:
        print()
        log("📦", "Fetching region task...")
        r = send_request(f"{SERVER_URL}/tasks/batch", headers=auth_headers)
        if r.status_code == 404:
            log("📦", "No more tasks available. Done.")
            break
        if r.status_code != 200:
            log("❌", f"Batch fetch failed: {r.status_code} - {r.text}")
            _time.sleep(10)
            continue
        batch = r.json()
        batch_id = batch["batch_id"]
        regions = batch["regions"]
        batch_count += 1

        if not regions:
            log("⚠️", "Empty batch, skipping")
            continue

        # Server now returns single region per batch
        region = regions[0]
        rx = int(region["region_x"])
        rz = int(region["region_z"])
        # Region corners in block coords (region is 512x512 blocks)
        x1 = rx * 512
        z1 = rz * 512
        x2 = rx * 512 + 511
        z2 = rz * 512 + 511

        log("⛏️ ", f"Batch #{batch_id}: Region ({rx}, {rz}) → corners ({x1},{z1})-({x2},{z2})")

        # Diagnostic: save + log state before Chunky runs
        save_resp = rcon.run("save-all")
        log("💾", f"Pre-save: {save_resp}")
        _time.sleep(3)
        sel_resp = rcon.run("chunky", "selection")
        log("🔍", f"Selection: {sel_resp}")
        pre_files = list(region_dir.glob("*.mca"))
        log("🔍", f"Region dir before: {len(pre_files)} files - {[f.name for f in pre_files]}")

        rcon.run("chunky", "world", "world")
        rcon.run("chunky", "dimension", dimension)
        chunky.set_corners(x1, z1, x2, z2)
        rcon.run("chunky", "shape", shape)
        rcon.run("chunky", "pattern", "loop")
        start_resp = rcon.run("chunky", "start")
        log("⛏️ ", f"Chunky: {start_resp}")

        import re as _re
        start_t = _time.time()
        last_log = 0.0
        seen_progress = False
        last_chunks_done = 0
        expected_chunks = 1024  # one full region = 32×32 chunks
        while True:
            elapsed = _time.time() - start_t
            if elapsed > 1800:
                log("⚠️ ", f"Region ({rx}, {rz}) timed out after 30min")
                chunky.cancel()
                break

            try:
                progress = chunky.status()
            except Exception as e:
                log("⚠️ ", f"Progress poll failed: {e}")
                _time.sleep(5)
                continue

            if elapsed - last_log >= 5.0:
                log("⛏️ ", f"[{elapsed:.0f}s] {progress}")
                last_log = elapsed

            pl = progress.lower()

            # Parse "123/456" format (old Chunky)
            m = _re.search(r'(\d[\d,]*)\s*/\s*(\d[\d,]*)', progress.replace(',', ''))
            if m:
                chunks_done = int(m.group(1))
                chunks_total = int(m.group(2))
                if chunks_total > 0:
                    expected_chunks = min(chunks_total, 1024)  # MCA header max = 1024 chunks
                last_chunks_done = chunks_done
                seen_progress = True
            else:
                # Parse "Processed: 587 chunks (53.90%)" format (newer Chunky)
                m2 = _re.search(r'(?:Processed|Finished|Generated)\s*:?\s*(\d[\d,]*)\s+chunks', progress.replace(',', ''))
                if m2:
                    chunks_done = int(m2.group(1))
                    last_chunks_done = chunks_done
                    seen_progress = True
                    mp = _re.search(r'\((\d+(?:\.\d+)?)%\)', progress)
                    if mp and chunks_done > 0:
                        pct = float(mp.group(1))
                        if pct > 0:
                            expected_chunks = min(int(chunks_done / (pct / 100)), 1024)
                else:
                    # Fallback: match any "NNN chunks (XX%)" pattern
                    m3 = _re.search(r'(\d[\d,]*)\s+chunks', progress.replace(',', ''))
                    if m3:
                        last_chunks_done = int(m3.group(1))
                        seen_progress = True
                        mp = _re.search(r'\((\d+(?:\.\d+)?)%\)', progress)
                        if mp and last_chunks_done > 0:
                            pct = float(mp.group(1))
                            if pct > 0:
                                expected_chunks = min(int(last_chunks_done / (pct / 100)), 1024)

            # Explicit completion keywords
            if elapsed > 3 and ("finished" in pl or "100%" in pl or "100.00%" in pl or "done" in pl):
                log("⛏️ ", f"Region ({rx}, {rz}) done in {elapsed:.1f}s ({last_chunks_done}/{expected_chunks} chunks)")
                break

            # All expected chunks generated
            if seen_progress and last_chunks_done >= expected_chunks and expected_chunks > 0:
                log("⛏️ ", f"Region ({rx}, {rz}) done ({last_chunks_done}/{expected_chunks} chunks) in {elapsed:.1f}s")
                break

            if "not running" in pl or "no tasks" in pl:
                if seen_progress:
                    log("⛏️ ", f"Region ({rx}, {rz}) done in {elapsed:.1f}s ({last_chunks_done}/{expected_chunks} chunks)")
                    break
                elif elapsed > 30:
                    log("⚠️ ", f"Region ({rx}, {rz}) — no progress after {elapsed:.0f}s, assuming done")
                    break

            _time.sleep(2.0)

        # Log region dir state after Chunky task
        post_files = list(region_dir.glob("*.mca"))
        log("🔍", f"Region dir after chunky: {len(post_files)} files - {[f.name for f in post_files]}")

        # ── Generation done — save + upload ──────────────────────────
        def _count_mca_chunks(path):
            """Count non-empty chunks in a .mca file (1024 header entries)."""
            try:
                with open(path, 'rb') as fh:
                    header = fh.read(4096)
                count = 0
                for i in range(1024):
                    offset_bytes = header[i*4:i*4+3]
                    if offset_bytes != b'\x00\x00\x00':
                        count += 1
                return count
            except Exception:
                return 0

        log("💾", "Saving world...")
        save_resp = rcon.run("save-all")
        log("💾", f"save-all: {save_resp}")
        _time.sleep(3)
        sel_resp = rcon.run("chunky", "selection")
        log("🔍", f"Selection after save: {sel_resp}")
        save_files = list(region_dir.glob("*.mca"))
        log("🔍", f"Region dir after save: {len(save_files)} files - {[f.name for f in save_files]}")
        _time.sleep(2)

        expected_file = region_dir / f"r.{rx}.{rz}.mca"
        found = []
        for attempt in range(60):
            if expected_file.exists():
                size1 = expected_file.stat().st_size
                _time.sleep(0.5)
                size2 = expected_file.stat().st_size
                if size1 == size2 and size1 > 0:
                    chunk_count = _count_mca_chunks(expected_file)
                    if chunk_count >= expected_chunks:
                        found.append(expected_file)
                        log("💾", f"{expected_file.name}: {chunk_count}/{expected_chunks} chunks OK")
                        break
                    else:
                        log("⚠️ ", f"{expected_file.name}: only {chunk_count}/{expected_chunks} chunks, waiting...")
            _time.sleep(1.0)
        else:
            log("⚠️ ", f"Expected {expected_file.name} not found/stable after 60s, checking all files...")
            for f in region_dir.glob("*.mca"):
                size1 = f.stat().st_size
                _time.sleep(0.5)
                size2 = f.stat().st_size
                if size1 == size2 and size1 > 0:
                    found.append(f)

        rcon.run("save-off")

        all_hashes = {}

        if not found:
            log("❌", f"No .mca files found for region ({rx}, {rz})")
            all_files = list(region_dir.glob("*.mca"))
            log("🔍", f"Files in region dir: {[f.name for f in all_files]}")
            # Still attempt hash submission even without files
        else:
            # ── Upload each found file ──────────────────────────────
            for mca_path in found:
                file_hash = hashlib.sha256()
                with open(mca_path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 64), b""):
                        file_hash.update(chunk)
                hex_hash = file_hash.hexdigest()

                try:
                    uploader.upload_file(batch_id, mca_path)
                    log("📤", f"Uploaded {mca_path.name} ({mca_path.stat().st_size} bytes)")
                    all_hashes[mca_path.name] = hex_hash

                    # Render + upload scale-1 tile (fast, 512x512 solid colors)
                    try:
                        from server.map_renderer import render_region_tile
                        log("🗺️", f"Rendering s1 tile for region ({rx}, {rz})...")
                        t0 = _time.time()
                        img = render_region_tile(mca_path, rx, rz, 1)
                        if img:
                            tile_path = mca_path.with_suffix(".png")
                            img.save(tile_path)
                            log("🗺️", f"Rendered s1 in {(_time.time()-t0):.1f}s, uploading...")
                            uploader.upload_tile(batch_id, tile_path, scale=1)
                            tile_path.unlink()
                            log("🗺️", f"Tile s1 uploaded for region ({rx}, {rz})")
                        else:
                            log("⚠️", f"Render s1 returned None for region ({rx}, {rz})")
                    except Exception as tile_err:
                        log("⚠️", f"Tile s1 render/upload failed: {tile_err}")

                    # Scale 16 textures in background (heavy: 8192x8192)
                    # NOTE: mca file must stay on disk until s16 thread finishes reading it
                    if texture_atlas is not None:
                        def _render_hires(mca=str(mca_path), rx=rx, rz=rz, bid=batch_id):
                            try:
                                from server.map_renderer import render_region_tile_textured
                                log("🗺️", f"[bg] Rendering s16 textures for region ({rx}, {rz})...")
                                t0 = _time.time()
                                big = render_region_tile_textured(Path(mca), rx, rz, texture_atlas, scale=16)
                                if big:
                                    big_path = Path(mca).with_suffix(".png")
                                    big.save(big_path)
                                    log("🗺️", f"[bg] Rendered s16 in {(_time.time()-t0):.1f}s, uploading...")
                                    uploader.upload_tile(bid, big_path, scale=16)
                                    big_path.unlink()
                                    log("🗺️", f"[bg] Tile s16 uploaded for region ({rx}, {rz})")
                                else:
                                    log("⚠️", f"[bg] Render s16 returned None for region ({rx}, {rz})")
                            except Exception as e:
                                log("⚠️", f"[bg] Tile s16 render/upload failed: {e}")
                            finally:
                                log("🗑️ ", f"Keeping {Path(mca).name}")
                        threading.Thread(target=_render_hires, daemon=True).start()
                    else:
                        log("🗑️ ", f"Keeping {mca_path.name} (no atlas)")
                except Exception as e:
                    log("❌", f"Upload failed for {mca_path.name}: {e}")

        # ── Submit hash for this batch ──────────────────────────
        if all_hashes:
            log("🔑", f"Submitting {len(all_hashes)} hash(es) for batch #{batch_id}...")
            try:
                submit_result = uploader.submit_hashes(batch_id, all_hashes)
                log("🔑", f"Submit result: {submit_result}")
            except Exception as e:
                log("❌", f"Hash submission failed: {e}")
        else:
            log("⚠️", f"No files uploaded for batch #{batch_id}, skipping hash submission")

        rcon.run("save-on")

    rcon.disconnect()
    mc_log_stop.set()
    server.stop()
    log("🛑", "Server stopped")

    print()
    print("=" * 50)
    log("✅", f"Done! {batch_count} batch(es) completed")
    print(f"  Dashboard: http://localhost:8000/admin")
    print(f"  Map:       http://localhost:8000/admin/map")
    print("=" * 50)


if __name__ == "__main__":
    main()
