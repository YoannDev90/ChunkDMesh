#!/usr/bin/env python3
"""ChunkDMesh launcher - run server and/or client from project root."""

import argparse
import asyncio
import os
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(ROOT, "server")
CLIENT_DIR = os.path.join(ROOT, "client")


def run_server(host="0.0.0.0", port=8000, world_config=None):
    os.environ["CHUNKMESH_HOST"] = host
    os.environ["CHUNKMESH_PORT"] = str(port)
    if world_config:
        os.environ["CHUNKMESH_CONFIG_PATH"] = os.path.abspath(world_config)
    os.chdir(SERVER_DIR)
    sys.path.insert(0, SERVER_DIR)
    from main import main

    asyncio.run(main())


def run_server_thread(host="0.0.0.0", port=8000, world_config=None):
    """Start server in a daemon thread (no TUI)."""
    os.environ["CHUNKMESH_HOST"] = host
    os.environ["CHUNKMESH_PORT"] = str(port)
    if world_config:
        os.environ["CHUNKMESH_CONFIG_PATH"] = os.path.abspath(world_config)

    def _server_loop():
        os.chdir(SERVER_DIR)
        sys.path.insert(0, SERVER_DIR)
        from main import main

        asyncio.run(main())

    t = threading.Thread(target=_server_loop, daemon=True)
    t.start()
    return t


def run_client(host=None, port=None, bg=False):
    connect_host = host if host and host != "0.0.0.0" else "127.0.0.1"
    connect_port = port or 8000
    os.environ["CHUNKMESH_SERVER_URL"] = f"http://{connect_host}:{connect_port}"
    if bg:
        os.environ["CHUNKMESH_CLIENT_BG"] = "1"
    os.chdir(CLIENT_DIR)
    sys.path.insert(0, CLIENT_DIR)
    from main import main as client_main

    client_main(bg=bg)


def run_both(host="0.0.0.0", port=8000, world_config=None):
    """Start server in background thread + client with unified TUI."""
    connect_host = host if host != "0.0.0.0" else "127.0.0.1"
    os.environ["CHUNKMESH_SERVER_URL"] = f"http://{connect_host}:{port}"

    # Start server in daemon thread
    run_server_thread(host, port, world_config)

    # Wait for server to be ready
    import time

    import httpx

    url = f"http://{connect_host}:{port}"
    print(f"  Waiting for server at {url}...")
    for _ in range(60):
        try:
            with httpx.Client(timeout=2) as c:
                if c.get(f"{url}/health").status_code == 200:
                    print("  Server is up")
                    break
        except Exception:
            pass
        time.sleep(1.0)
    else:
        print("  Server failed to start")
        sys.exit(1)

    # Start client with unified TUI
    os.chdir(CLIENT_DIR)
    sys.path.insert(0, CLIENT_DIR)
    from both_tui import BothTUI
    from client_tui import ClientTUI
    from main import main as client_main

    client_tui = ClientTUI()
    both_tui = BothTUI(client_tui)

    # Patch client_tui module-level functions to route through client_tui instance
    import client_tui as ct_mod

    ct_mod.tui = client_tui

    # Start unified TUI in a thread
    tui_thread = threading.Thread(target=both_tui.run, daemon=True)
    tui_thread.start()

    # Run client logic (bg=True skips client's own TUI thread)
    client_main(bg=True)

    both_tui.stop()
    tui_thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description="ChunkDMesh launcher")
    parser.add_argument(
        "component",
        choices=["server", "client", "both"],
        help="What to launch: 'server', 'client', or 'both' (parallel)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Server bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )
    parser.add_argument(
        "--world-config",
        help="Path to world config JSON5 file",
    )
    parser.add_argument(
        "--bg",
        "--background",
        action="store_true",
        help="Run client in background mode (no TUI)",
    )
    args = parser.parse_args()

    if args.component == "server":
        run_server(args.host, args.port, args.world_config)
    elif args.component == "client":
        run_client(args.host, args.port, bg=args.bg)
    elif args.component == "both":
        run_both(args.host, args.port, args.world_config)


if __name__ == "__main__":
    main()
