"""Shared server state for TUI and monitoring."""

import dataclasses
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from constants import RECENT_REQUESTS_MAX

LOG_BUFFER_MAX = 100


@dataclass
class ServerStats:
    start_time: float = time.time()
    request_count: int = 0
    active_clients: int = 0
    pending_tasks: int = 0
    assigned_tasks: int = 0
    working_tasks: int = 0
    completed_tasks: int = 0
    validated_tasks: int = 0
    total_storage_mb: float = 0.0
    last_request_path: str = ""
    last_request_status: int = 0
    world_config: dict = field(default_factory=dict)


class ServerState:
    def __init__(self):
        self._lock = threading.Lock()
        self.stats = ServerStats()
        self._recent_requests: list[tuple[float, str, int]] = []
        self._log_buffer: deque[tuple[str, str, str]] = deque(maxlen=LOG_BUFFER_MAX)

    def record_request(self, path: str, status: int):
        with self._lock:
            self.stats.request_count += 1
            self.stats.last_request_path = path
            self.stats.last_request_status = status
            self._recent_requests.append((time.time(), path, status))
            if len(self._recent_requests) > RECENT_REQUESTS_MAX:
                self._recent_requests.pop(0)

    def log(self, icon: str, msg: str):
        ts = time.strftime("%H:%M:%S")
        with self._lock:
            self._log_buffer.append((ts, icon, msg))

    def recent_logs(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(self._log_buffer)

    def update_task_counts(self, pending=0, assigned=0, working=0, completed=0, validated=0):
        with self._lock:
            self.stats.pending_tasks = pending
            self.stats.assigned_tasks = assigned
            self.stats.working_tasks = working
            self.stats.completed_tasks = completed
            self.stats.validated_tasks = validated

    def update_storage(self, total_mb: float):
        with self._lock:
            self.stats.total_storage_mb = total_mb

    def update_clients(self, count: int):
        with self._lock:
            self.stats.active_clients = count

    def set_world_config(self, config: dict):
        with self._lock:
            self.stats.world_config = config

    def snapshot(self) -> ServerStats:
        with self._lock:
            return dataclasses.replace(self.stats)

    def recent_requests(self) -> list[tuple[float, str, int]]:
        with self._lock:
            return list(self._recent_requests)


server_state = ServerState()
