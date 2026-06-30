import logging
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class RegionWatcher:
    """Poll-based watcher for region file changes.

    Uses polling instead of inotify for portability.
    Checks mtime of each .mca file every `interval` seconds.
    """

    def __init__(
        self, region_dir: str, on_change: Callable[[int, int], None], interval: float = 5.0
    ):
        self.region_dir = Path(region_dir)
        self.on_change = on_change
        self.interval = interval
        self._mtimes: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Region watcher started (poll %ss)", self.interval)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("Region watcher stopped")

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                self._check_changes()
            except Exception as e:
                logger.error("Region watcher error: %s", e)
            self._stop_event.wait(self.interval)

    def _check_changes(self):
        if not self.region_dir.exists():
            return

        for f in self.region_dir.glob("r.*.*.mca"):
            try:
                mtime = f.stat().st_mtime
                prev = self._mtimes.get(f.name)
                if prev is not None and mtime != prev:
                    parts = f.stem.split(".")
                    if len(parts) >= 3:
                        try:
                            rx, rz = int(parts[1]), int(parts[2])
                            logger.info("Region changed: %s", f.name)
                            self.on_change(rx, rz)
                        except ValueError:
                            pass
                self._mtimes[f.name] = mtime
            except OSError:
                pass
