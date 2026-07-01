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
        """Open TCP connection to RCON server."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.host, self.port))

    def _next_id(self) -> int:
        self._id_counter += 1
        if self._id_counter > 2147483647:
            self._id_counter = 1
        return self._id_counter

    def _send(self, req_id: int, pkt_type: int, body: bytes) -> None:
        """Send an RCON packet with length prefix."""
        payload = struct.pack("<ii", req_id, pkt_type) + body + b"\x00\x00"
        packet = struct.pack("<i", len(payload)) + payload
        self._sock.sendall(packet)

    def _recv(self) -> tuple[int, int, bytes]:
        """Receive and parse an RCON packet."""
        size_data = self._recv_exact(4)
        size = struct.unpack("<i", size_data)[0]
        data = self._recv_exact(size)
        req_id = struct.unpack("<i", data[0:4])[0]
        pkt_type = struct.unpack("<i", data[4:8])[0]
        body = data[8:-2]
        return req_id, pkt_type, body

    def _recv_exact(self, n: int) -> bytes:
        """Read exactly n bytes from socket, retrying as needed."""
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("Connection closed by remote")
            buf += chunk
        return buf

    def login(self) -> bool:
        """Authenticate with RCON server using password.

        Returns: True on success.

        Raises: PermissionError if auth fails.
        """
        self._send(self._next_id(), 3, self.password.encode("utf-8"))
        req_id, pkt_type, _ = self._recv()
        if req_id == -1:
            raise PermissionError("RCON auth failed: wrong password")
        return True

    def run(self, command: str) -> str:
        """Send an RCON command and return response.

        Args:
            command: Command string.

        Returns: Response text.
        """
        self._send(self._next_id(), 2, command.encode("utf-8"))
        req_id, pkt_type, body = self._recv()
        return body.decode("utf-8", errors="replace")

    def close(self) -> None:
        """Close the RCON socket connection."""
        if self._sock:
            with contextlib.suppress(Exception):
                self._sock.close()
            self._sock = None


class RCONConnection:
    """High-level RCON connection with retry logic."""

    def __init__(self, host: str = "127.0.0.1", port: int = 25575, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._client: _RCONSocket | None = None

    def connect(self, retries: int = 10, delay: float = 2.0) -> bool:
        """Connect to RCON with retries.

        Args:
            retries: Number of connection attempts.
            delay: Seconds between attempts.

        Returns: True if connected.
        """
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
        """Execute a command via RCON.

        Args:
            command: Command name.
            *args: Command arguments.

        Returns: Command response text.

        Raises: RuntimeError if not connected.
        """
        if not self._client:
            raise RuntimeError("RCON not connected")
        full_cmd = " ".join([command] + list(args))
        logger.info("RCON command: %s", full_cmd)
        response = self._client.run(full_cmd)
        logger.info("RCON response: %s", response)
        return response

    def disconnect(self) -> None:
        """Disconnect from RCON server."""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("RCON disconnected")

    @property
    def connected(self) -> bool:
        """Check if RCON client is connected."""
        return self._client is not None


class ChunkyController:
    """Controls Chunky generation via RCON commands."""

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
        """Start Chunky generation with given parameters.

        Args:
            world: World name.
            radius: Optional radius in chunks.
            center_x, center_z: Optional center coordinates.
            shape: Optional shape (square, circle, etc.).
            dimension: Optional dimension name.

        Returns: Command response string.
        """
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
        """Pause Chunky generation."""
        return self.rcon.run("chunky", "pause")

    def resume(self) -> str:
        """Resume paused Chunky generation."""
        return self.rcon.run("chunky", "resume")

    def cancel(self) -> str:
        """Cancel running Chunky generation."""
        return self.rcon.run("chunky", "cancel")

    def status(self) -> str:
        """Get Chunky progress status string."""
        return self.rcon.run("chunky", "progress")

    def set_corners(self, x1: int, z1: int, x2: int, z2: int) -> str:
        """Set Chunky generation corners.

        Args:
            x1, z1: First corner coordinates.
            x2, z2: Second corner coordinates.

        Returns: Command response.
        """
        resp = self.rcon.run("chunky", "corners", str(x1), str(z1), str(x2), str(z2))
        logger.info("chunky corners %d %d %d %d -> %s", x1, z1, x2, z2, resp)
        return resp

    def set_radius(self, radius: int) -> str:
        """Set Chunky radius.

        Args:
            radius: Radius in chunks.

        Returns: Command response.
        """
        return self.rcon.run("chunky", "radius", str(radius))

    def set_center(self, x: int, z: int) -> str:
        """Set Chunky center point.

        Args:
            x: Center X coordinate.
            z: Center Z coordinate.

        Returns: Command response.
        """
        return self.rcon.run("chunky", "center", str(x), str(z))

    def set_shape(self, shape: str) -> str:
        """Set Chunky generation shape.

        Args:
            shape: Shape name (square, circle, etc.).

        Returns: Command response.
        """
        return self.rcon.run("chunky", "shape", shape)

    def set_dimension(self, dimension: str) -> str:
        """Set Chunky dimension.

        Args:
            dimension: Dimension name.

        Returns: Command response.
        """
        return self.rcon.run("chunky", "dimension", dimension)

    def list_processes(self) -> str:
        """List running Chunky processes."""
        return self.rcon.run("chunky", "list")

    def get_help(self) -> str:
        """Get Chunky help text."""
        return self.rcon.run("chunky", "help")

    def wait_generation_done(self, poll_interval: float = 5.0, timeout: float = 7200) -> bool:
        """Poll Chunky progress until generation finishes.

        Args:
            poll_interval: Seconds between progress checks.
            timeout: Max seconds to wait.

        Returns: True if generation completed.
        """
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
