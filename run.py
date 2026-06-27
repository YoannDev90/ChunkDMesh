#!/usr/bin/env python3
"""ChunkDMesh launcher - run server and/or client from project root."""

import argparse
import asyncio
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(ROOT, "server")
CLIENT_DIR = os.path.join(ROOT, "client")


def run_server():
    os.chdir(SERVER_DIR)
    sys.path.insert(0, SERVER_DIR)
    from main import main
    asyncio.run(main())


def run_client():
    os.chdir(CLIENT_DIR)
    sys.path.insert(0, CLIENT_DIR)
    from main import main as client_main
    client_main()


def main():
    parser = argparse.ArgumentParser(description="ChunkDMesh launcher")
    parser.add_argument(
        "component",
        choices=["server", "client", "both"],
        help="What to launch: 'server', 'client', or 'both' (parallel)",
    )
    args = parser.parse_args()

    if args.component == "server":
        run_server()
    elif args.component == "client":
        run_client()
    elif args.component == "both":
        import subprocess
        import signal

        server_proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "run.py"), "server"],
            cwd=ROOT,
        )
        client_proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "run.py"), "client"],
            cwd=ROOT,
        )

        def shutdown(sig, frame):
            server_proc.terminate()
            client_proc.terminate()

        signal.signal(signal.SIGINT, shutdown)
        signal.signal(signal.SIGTERM, shutdown)

        server_proc.wait()
        client_proc.wait()


if __name__ == "__main__":
    main()
