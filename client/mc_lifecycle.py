"""MC server lifecycle: launch, log streaming, RCON connection."""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from rcon_client import ChunkyController, RCONConnection


class MCLifecycle:
    def __init__(self, server_dir: Path, java_bin: Path, jar_path: Path, asset_mgr, seed: int, mc_version: str, log_fn):
        self.server_dir = server_dir
        self.java_bin = java_bin
        self.jar_path = jar_path
        self.asset_mgr = asset_mgr
        self.seed = seed
        self.mc_version = mc_version
        self.log = log_fn

        self.server = None
        self.rcon: RCONConnection | None = None
        self.chunky: ChunkyController | None = None
        self._mc_log_stop = threading.Event()
        self._mc_log_pos = 0

    def start_server(self, measure_ctx=None) -> bool:
        from instance_runner import MCServer

        self.asset_mgr.write_server_properties(seed=self.seed)
        self.log("🚀", f"server.properties written (seed={self.seed}, RCON enabled)")
        self.server = MCServer(
            server_dir=self.server_dir,
            java_bin=self.java_bin,
            jar_path=self.jar_path,
            xmx_mb=4096,
            xms_mb=1024,
        )
        ctx = measure_ctx or _NullContext()
        with ctx:
            self.server.start()
        self.log("🚀", f"Server process PID: {self.server.get_pid()}")
        return True

    def start_log_stream(self) -> None:
        self._mc_log_pos = 0
        mc_log_path = self.server_dir / "logs" / "latest.log"
        if mc_log_path.exists():
            self._mc_log_pos = mc_log_path.stat().st_size

        def _stream():
            while not self._mc_log_stop.is_set():
                try:
                    if mc_log_path.exists():
                        with open(mc_log_path) as f:
                            f.seek(self._mc_log_pos)
                            lines = f.readlines()
                            self._mc_log_pos = f.tell()
                            for line in lines:
                                line = line.rstrip()
                                if not line:
                                    continue
                                msg = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*\[[^\]]+\]\s*:\s*", "", line)
                                self.log("📜", msg)
                except Exception:
                    pass
                time.sleep(1.0)

        t = threading.Thread(target=_stream, daemon=True)
        t.start()

    def wait_until_ready(self, timeout: float = 300) -> bool:
        return self.server.wait_until_ready(timeout=timeout)

    def restart_for_rcon(self) -> bool:
        mc_log_path = self.server_dir / "logs" / "latest.log"
        self._mc_log_stop.set()
        self.server.stop()
        self._mc_log_pos = mc_log_path.stat().st_size if mc_log_path.exists() else 0
        self._mc_log_stop.clear()

        self.asset_mgr.write_server_properties()
        from instance_runner import MCServer

        self.server = MCServer(
            server_dir=self.server_dir,
            java_bin=self.java_bin,
            jar_path=self.jar_path,
            xmx_mb=4096,
            xms_mb=1024,
        )
        self.start_log_stream()
        self.server.start()
        return self.wait_until_ready(timeout=300)

    def check_rcon_enabled(self) -> bool:
        rcon_props_path = self.server_dir / "server.properties"
        if rcon_props_path.exists():
            with open(rcon_props_path) as f:
                return "enable-rcon=true" in f.read()
        return False

    def connect_rcon(self, rcon_password: str, retries: int = 15, delay: float = 2.0) -> bool:
        self.rcon = RCONConnection(host="127.0.0.1", port=25575, password=rcon_password)
        if not self.rcon.connect(retries=retries, delay=delay):
            return False
        self.chunky = ChunkyController(self.rcon)
        self.log("🔗", "RCON connected")
        return True

    def stop(self):
        if self.rcon:
            self.rcon.disconnect()
        self._mc_log_stop.set()
        if self.server:
            self.server.stop()


class _NullContext:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass
