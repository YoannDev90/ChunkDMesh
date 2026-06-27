import asyncio
import logging
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DONE_PATTERN = "Done"
READY_PATTERNS = [
    "Done",
    "RCON listener started",
    "Timings Reset",
]


class MCServer:
    def __init__(
        self,
        server_dir: Path,
        java_bin: Path,
        jar_path: Path,
        xmx_mb: int = 4096,
        xms_mb: int = 1024,
        extra_jvm_args: list[str] | None = None,
    ):
        self.server_dir = server_dir
        self.java_bin = java_bin
        self.jar_path = jar_path
        self.xmx_mb = xmx_mb
        self.xms_mb = xms_mb
        self.extra_jvm_args = extra_jvm_args or []

        self._process: Optional[subprocess.Popen] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._ready = False
        self._stopped = False
        self._log_lines: list[str] = []
        self._on_ready: Optional[Callable] = None
        self._on_line: Optional[Callable[[str], None]] = None

    def _build_command(self) -> list[str]:
        cmd = [
            str(self.java_bin),
            f"-Xmx{self.xmx_mb}M",
            f"-Xms{self.xms_mb}M",
            "-XX:+UseG1GC",
            "-XX:+ParallelRefProcEnabled",
            "-Dcom.mojang.eula.agree=true",
            *self.extra_jvm_args,
            "-jar",
            str(self.jar_path),
            "nogui",
        ]
        return cmd

    def start(self, on_ready: Optional[Callable] = None, on_line: Optional[Callable[[str], None]] = None):
        if self._process and self._process.poll() is None:
            raise RuntimeError("Server is already running")

        self._ready = False
        self._stopped = False
        self._log_lines.clear()
        self._on_ready = on_ready
        self._on_line = on_line

        cmd = self._build_command()
        logger.info("Starting server: %s", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            cwd=str(self.server_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        self._stdout_thread = threading.Thread(target=self._read_output, daemon=True)
        self._stdout_thread.start()

    def _read_output(self):
        assert self._process and self._process.stdout
        for line in iter(self._process.stdout.readline, ""):
            line = line.rstrip("\n\r")
            if not line:
                continue

            self._log_lines.append(line)
            logger.info("[MC] %s", line)

            if self._on_line:
                try:
                    self._on_line(line)
                except Exception:
                    pass

            if not self._ready:
                for pattern in READY_PATTERNS:
                    if pattern in line:
                        self._ready = True
                        logger.info("Server is ready!")
                        if self._on_ready:
                            try:
                                self._on_ready()
                            except Exception:
                                pass
                        break

    def wait_until_ready(self, timeout: float = 300) -> bool:
        start = time.time()
        while not self._ready:
            if self._process and self._process.poll() is not None:
                logger.error("Server process exited with code %s", self._process.returncode)
                return False
            if time.time() - start > timeout:
                logger.error("Server did not become ready within %ss", timeout)
                return False
            time.sleep(0.5)
        return True

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def send_command(self, command: str):
        if not self.is_running():
            raise RuntimeError("Server is not running")
        if not self._process.stdin:
            raise RuntimeError("Server stdin not available")
        logger.info("Sending command: %s", command)
        self._process.stdin.write(command + "\n")
        self._process.stdin.flush()

    def stop(self, timeout: float = 30):
        if not self.is_running():
            return

        self._stopped = True
        logger.info("Stopping server...")

        self.send_command("stop")

        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning("Server did not stop gracefully, killing...")
            self._process.kill()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.error("Failed to kill server process")

        if self._stdout_thread:
            self._stdout_thread.join(timeout=5)

        logger.info("Server stopped")

    def get_log_lines(self, last_n: Optional[int] = None) -> list[str]:
        if last_n:
            return self._log_lines[-last_n:]
        return list(self._log_lines)

    def get_pid(self) -> Optional[int]:
        if self._process:
            return self._process.pid
        return None
