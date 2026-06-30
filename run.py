#!/usr/bin/env python3
"""ChunkDMesh launcher - run server and/or client from project root."""

import argparse
import asyncio
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(ROOT, "server")
CLIENT_DIR = os.path.join(ROOT, "client")


def run_server(host="0.0.0.0", port=8000, world_config=None, raw_cli=False):
    os.environ["CHUNKMESH_HOST"] = host
    os.environ["CHUNKMESH_PORT"] = str(port)
    if world_config:
        os.environ["CHUNKMESH_CONFIG_PATH"] = os.path.abspath(world_config)
    if raw_cli:
        os.environ["CHUNKMESH_RAW_CLI"] = "1"
    os.chdir(SERVER_DIR)
    sys.path.insert(0, SERVER_DIR)
    from main import main
    asyncio.run(main(raw_cli=raw_cli))


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


def main():
    parser = argparse.ArgumentParser(description="ChunkDMesh launcher")
    parser.add_argument(
        "component",
        choices=["server", "client", "both"],
        help="What to launch: 'server', 'client', or 'both' (parallel)",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Server bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Server port (default: 8000)",
    )
    parser.add_argument(
        "--world-config",
        help="Path to world config JSON5 file",
    )
    parser.add_argument(
        "--bg", "--background", action="store_true",
        help="Run client in background mode (no TUI)",
    )
    parser.add_argument(
        "--raw-cli", action="store_true",
        help="Run server in raw CLI mode (no TUI, plain output)",
    )
    args = parser.parse_args()

    if args.component == "server":
        run_server(args.host, args.port, args.world_config, raw_cli=args.raw_cli)
    elif args.component == "client":
        run_client(args.host, args.port, bg=args.bg)
    elif args.component == "both":
        import subprocess
        import signal

        cmd = [sys.executable, os.path.join(ROOT, "run.py")]
        svr_cmd = [*cmd, "server"]
        cli_cmd = [*cmd, "client"]
        if args.host:
            svr_cmd.extend(["--host", args.host])
            cli_cmd.extend(["--host", args.host])
        svr_cmd.extend(["--port", str(args.port)])
        cli_cmd.extend(["--port", str(args.port)])
        if args.world_config:
            svr_cmd.extend(["--world-config", args.world_config])
        if args.raw_cli:
            svr_cmd.append("--raw-cli")
        if args.bg:
            cli_cmd.append("--bg")

        server_proc = subprocess.Popen(svr_cmd, cwd=ROOT)
        client_proc = subprocess.Popen(cli_cmd, cwd=ROOT)

        def shutdown(sig, frame):
            server_proc.terminate()
            client_proc.terminate()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        server_proc.wait()
        client_proc.wait()


if __name__ == "__main__":
    main()
