import contextlib
import logging
import socket
import struct
import time

logger = logging.getLogger(__name__)

TERMINATOR = b"\x00\x00"


class _RCONSocket:
    """Raw RCON protocol over TCP socket."""

    def __init__(self, host: str, port: int, password: str, timeout: float = 10):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._id_counter = 0

    def connect(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.host, self.port))

    def _next_id(self) -> int:
        self._id_counter += 1
        if self._id_counter > 2147483647:
            self._id_counter = 1
        return self._id_counter

    def _send(self, req_id: int, pkt_type: int, body: bytes) -> None:
        payload = struct.pack("<ii", req_id, pkt_type) + body + b"\x00\x00"
        packet = struct.pack("<i", len(payload)) + payload
        self._sock.sendall(packet)

    def _recv(self) -> tuple[int, int, bytes]:
        size_data = self._recv_exact(4)
        size = struct.unpack("<i", size_data)[0]
        data = self._recv_exact(size)
        req_id = struct.unpack("<i", data[0:4])[0]
        pkt_type = struct.unpack("<i", data[4:8])[0]
        body = data[8:-2]
        return req_id, pkt_type, body

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by remote")
            buf += chunk
        return buf

    def login(self) -> bool:
        self._send(self._next_id(), 3, self.password.encode("utf-8"))
        req_id, pkt_type, _ = self._recv()
        if req_id == -1:
            raise PermissionError("RCON auth failed: wrong password")
        return True

    def run(self, command: str) -> str:
        self._send(self._next_id(), 2, command.encode("utf-8"))
        req_id, pkt_type, body = self._recv()
        return body.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self._sock:
            with contextlib.suppress(Exception):
                self._sock.close()
            self._sock = None


class RCONConnection:
    def __init__(self, host: str = "127.0.0.1", port: int = 25575, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._client: _RCONSocket | None = None

    def connect(self, retries: int = 10, delay: float = 2.0) -> bool:
        for attempt in range(1, retries + 1):
            try:
                self._client = _RCONSocket(self.host, self.port, self.password, timeout=10)
                self._client.connect()
                self._client.login()
                logger.info("RCON connected to %s:%d", self.host, self.port)
                return True
            except Exception as e:
                logger.warning("RCON attempt %d/%d failed: %s", attempt, retries, e)
                if self._client:
                    self._client.close()
                    self._client = None
                time.sleep(delay)

        logger.error("Failed to connect to RCON after %d attempts", retries)
        return False

    def run(self, command: str, *args: str) -> str:
        if not self._client:
            raise RuntimeError("RCON not connected")
        full_cmd = " ".join([command] + list(args))
        logger.info("RCON command: %s", full_cmd)
        response = self._client.run(full_cmd)
        logger.info("RCON response: %s", response)
        return response

    def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            logger.info("RCON disconnected")

    @property
    def connected(self) -> bool:
        return self._client is not None


class ChunkyController:
    def __init__(self, rcon: RCONConnection):
        self.rcon = rcon

    def start(
        self,
        world: str = "world",
        radius: int | None = None,
        center_x: int | None = None,
        center_z: int | None = None,
        shape: str | None = None,
        dimension: str | None = None,
    ) -> str:
        # IMPORTANT: 'chunky world' MUST come first.
        # It loads the world's saved config which overwrites session settings.
        if world:
            resp = self.rcon.run("chunky", "world", world)
            logger.info("chunky world -> %s", resp)
        if dimension:
            resp = self.rcon.run("chunky", "dimension", dimension)
            logger.info("chunky dimension -> %s", resp)
        if center_x is not None and center_z is not None:
            resp = self.rcon.run("chunky", "center", str(center_x), str(center_z))
            logger.info("chunky center %d %d -> %s", center_x, center_z, resp)
        if radius is not None:
            resp = self.rcon.run("chunky", "radius", str(radius))
            logger.info("chunky radius %d -> %s", radius, resp)
        if shape:
            resp = self.rcon.run("chunky", "shape", shape)
            logger.info("chunky shape %s -> %s", shape, resp)
        resp = self.rcon.run("chunky", "start")
        logger.info("chunky start -> %s", resp)
        return resp

    def pause(self) -> str:
        return self.rcon.run("chunky", "pause")

    def resume(self) -> str:
        return self.rcon.run("chunky", "resume")

    def cancel(self) -> str:
        return self.rcon.run("chunky", "cancel")

    def status(self) -> str:
        return self.rcon.run("chunky", "progress")

    def set_corners(self, x1: int, z1: int, x2: int, z2: int) -> str:
        resp = self.rcon.run("chunky", "corners", str(x1), str(z1), str(x2), str(z2))
        logger.info("chunky corners %d %d %d %d -> %s", x1, z1, x2, z2, resp)
        return resp

    def set_radius(self, radius: int) -> str:
        return self.rcon.run("chunky", "radius", str(radius))

    def set_center(self, x: int, z: int) -> str:
        return self.rcon.run("chunky", "center", str(x), str(z))

    def set_shape(self, shape: str) -> str:
        return self.rcon.run("chunky", "shape", shape)

    def set_dimension(self, dimension: str) -> str:
        return self.rcon.run("chunky", "dimension", dimension)

    def list_processes(self) -> str:
        return self.rcon.run("chunky", "list")

    def get_help(self) -> str:
        return self.rcon.run("chunky", "help")

    def wait_generation_done(self, poll_interval: float = 5.0, timeout: float = 7200) -> bool:
        start = time.time()
        was_running = False

        while True:
            elapsed = time.time() - start
            if elapsed > timeout:
                logger.error("Generation timed out after %ss", timeout)
                return False

            try:
                progress = self.status()
            except Exception as e:
                logger.warning("Failed to get progress: %s", e)
                time.sleep(poll_interval)
                continue

            logger.info("Chunky progress: %s", progress)

            if "running" in progress.lower() or "generating" in progress.lower():
                was_running = True
            elif was_running and (
                "done" in progress.lower() or "finished" in progress.lower() or "not running" in progress.lower()
            ):
                logger.info("Generation completed!")
                return True

            time.sleep(poll_interval)
