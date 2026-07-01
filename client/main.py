"""ChunkDMesh Client - Worker that connects to the orchestrator and generates chunks."""

import argparse
import contextlib
import os
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

SERVER_URL = os.environ.get("CHUNKMESH_SERVER_URL", "http://localhost:8000")

from client_tui import (  # noqa: E402
    log,
    set_batch_count,
    set_power_score,
    set_progress,
    set_region,
    set_server_url,
    set_status,
    tui,
)
from monitor import export_otel_console, monitor, sample_system  # noqa: E402

HEARTBEAT_INTERVAL = 15


def main(bg: bool = False, compile_mcmap: bool = False):
    from mc_lifecycle import MCLifecycle
    from provisioner import Provisioner
    from utils import ResourceReportFormat, get_available_resources_averaged
    from work_loop import run_work_loop, send_request

    set_server_url(SERVER_URL)

    if not bg:
        import threading as _t

        tui_thread = _t.Thread(target=tui.run, daemon=True)
        tui_thread.start()

    # ── Wait for server ──────────────────────────────────────
    set_status("connecting")
    log("⏳", f"Waiting for server at {SERVER_URL}...")
    with monitor.measure("wait_for_server"):
        if not _wait_for_server(SERVER_URL):
            log("❌", "Server unreachable after 120s, aborting.")
            if not bg:
                tui.stop()
            return
    set_status("connected")

    # ── Power score ─────────────────────────────────────────
    log("📊", "Power score...")
    with monitor.measure("power_score"):
        power_score = get_available_resources_averaged(print_output=False, return_format=ResourceReportFormat.VALUE)
    set_power_score(power_score)
    log("📊", f"Score: {power_score:.2f}")

    # ── Login ──────────────────────────────────────────────
    set_status("login")
    log("🔑", "Logging in...")
    with monitor.measure("login"):
        r = send_request(
            f"{SERVER_URL}/auth/login",
            method="POST",
            payload={"power_score": power_score},
        )
    if r.status_code != 200:
        log("❌", f"Login failed: {r.status_code} - {r.text}")
        if not bg:
            tui.stop()
        return
    token = r.json()["token"]
    log("🔑", "Token acquired")

    # ── Provisioning ────────────────────────────────────────
    provisioner = Provisioner(SERVER_URL, token, log_fn=log)

    set_status("config")
    log("⚙️ ", "Fetching config...")
    with monitor.measure("fetch_config"):
        config = provisioner.fetch_config()
    if not config:
        if not bg:
            tui.stop()
        return

    mc_version = config.get("minecraft_version", "1.20.4")
    loader = config.get("minecraft_loader", "fabric")
    loader_version = config.get("loader_version", "0.19.3")
    seed = config.get("seed", 0)
    shape = config.get("shape", "square")
    dimension = config.get("dimension", "overworld")

    set_status("java")
    log("☕", "Detecting Java...")
    with monitor.measure("ensure_java"):
        java_bin = provisioner.setup_java(mc_version)

    from asset_manager import AssetManager

    work_dir = Path.home() / ".chunkdmesh" / "work"
    asset_mgr = AssetManager(SERVER_URL, token, work_dir=work_dir)

    set_status("setup")
    log("📁", "Setting up server...")
    with monitor.measure("setup_server"):
        server_dir = provisioner.setup_server(asset_mgr, mc_version, loader, loader_version)

    set_status("mods")
    log("📥", "Downloading mods...")
    with monitor.measure("download_mods"):
        if not provisioner.download_mods(asset_mgr, config, mc_version, loader):
            if not bg:
                tui.stop()
            return

    log("🔧", f"Installing {loader} {loader_version}...")
    with monitor.measure("install_loader"):
        jar_path = provisioner.install_loader(asset_mgr, mc_version, loader, loader_version)
        if not jar_path:
            log("❌", "Loader install failed")
            if not bg:
                tui.stop()
            return

    # Download palette files for client-side tile generation
    log("🎨", "Downloading palettes for tile generation...")
    provisioner.download_palettes(work_dir)

    # Set up mcmap binary (compile from source or download pre-built)
    log("🗺️ ", "Setting up mcmap...")
    provisioner.setup_mcmap(work_dir, auto_compile=compile_mcmap)

    # ── MC lifecycle ────────────────────────────────────────
    lifecycle = MCLifecycle(server_dir, java_bin, jar_path, asset_mgr, seed, mc_version, log_fn=log)

    set_status("launching")
    log("🚀", "Launching server...")
    with monitor.measure("server_start"):
        lifecycle.start_server()

    lifecycle.start_log_stream()

    with monitor.measure("wait_ready"):
        if not lifecycle.wait_until_ready(timeout=300):
            log("❌", "Server failed to start within 300s")
            lifecycle.stop()
            if not bg:
                tui.stop()
            return

    if not lifecycle.check_rcon_enabled():
        log("🚀", "RCON not in server.properties, restarting...")
        with monitor.measure("server_restart"):
            if not lifecycle.restart_for_rcon():
                log("❌", "Server failed to restart with RCON")
                lifecycle.stop()
                if not bg:
                    tui.stop()
                return

    log("🚀", "Server is ready!")
    set_status("ready")

    log("🔗", "Connecting RCON...")
    rcon_password = asset_mgr.get_rcon_password()
    with monitor.measure("rcon_connect"):
        if not lifecycle.connect_rcon(rcon_password):
            log("❌", "RCON connection failed")
            lifecycle.stop()
            if not bg:
                tui.stop()
            return

    # ── Heartbeat ───────────────────────────────────────────
    heartbeat_stop = threading.Event()

    def _heartbeat_loop():
        while not heartbeat_stop.is_set():
            with contextlib.suppress(Exception):
                send_request(f"{SERVER_URL}/heartbeat", method="POST", headers=provisioner.auth_headers)
            heartbeat_stop.wait(HEARTBEAT_INTERVAL)

    heartbeat_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    # ── Work loop ───────────────────────────────────────────
    set_status("ready")
    from uploader import RegionUploader

    uploader = RegionUploader(SERVER_URL, token)

    # Initialize client-side tile generator (mcmap)
    tiler = None
    from tiler import ClientTiler

    tiler = ClientTiler.from_work_dir(work_dir)
    if tiler:
        log("🗺️ ", "Client-side tile generation: enabled")
    else:
        log("🗺️ ", "Client-side tile generation: disabled (mcmap not available)")

    batch_count = run_work_loop(
        server_url=SERVER_URL,
        auth_headers=provisioner.auth_headers,
        dimension=dimension,
        server_dir=server_dir,
        rcon=lifecycle.rcon,
        chunky=lifecycle.chunky,
        uploader=uploader,
        shape=shape,
        monitor=monitor,
        log_fn=log,
        set_status_fn=set_status,
        set_region_fn=set_region,
        set_progress_fn=set_progress,
        set_batch_count_fn=set_batch_count,
        tiler=tiler,
    )

    # ── Cleanup ─────────────────────────────────────────────
    heartbeat_stop.set()
    lifecycle.stop()
    log("🛑", "Server stopped")

    export_otel_console(monitor.steps(), sample_system())

    log("✅", f"Done! {batch_count} batch(es) completed")
    log("🌐", "Dashboard: http://localhost:8000/admin")
    log("🌐", "Map:       http://localhost:8000/admin/map")

    set_status("done")
    if not bg:
        time.sleep(2)
        tui.stop()


def _wait_for_server(url: str, max_wait: float = 120.0) -> bool:
    import httpx

    delay = 0.5
    start = time.time()
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChunkDMesh Client")
    parser.add_argument("--bg", "--background", action="store_true", help="Run in background mode (no TUI)")
    parser.add_argument("--compile-mcmap", action="store_true", help="Compile mcmap from source instead of downloading")
    args = parser.parse_args()
    main(bg=args.bg, compile_mcmap=args.compile_mcmap)
