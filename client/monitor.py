"""Per-step resource monitoring using /proc (no psutil). OTEL-compatible export."""

import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

PROC = Path("/proc")
SELF_STAT = PROC / "self" / "stat"
SELF_STATUS = PROC / "self" / "status"
SELF_IO = PROC / "self" / "io"
PROC_LOADAVG = PROC / "loadavg"
PROC_MEMINFO = PROC / "meminfo"


@dataclass
class StepSnapshot:
    """Snapshot of resource usage for a single step."""

    name: str
    wall_s: float = 0.0
    cpu_s: float = 0.0
    rss_kb_delta: int = 0
    read_bytes: int = 0
    write_bytes: int = 0
    thread_count: int = 0


@dataclass
class SystemSample:
    """Snapshot of system-wide CPU load and memory."""

    cpu_load_1: float = 0.0
    cpu_load_5: float = 0.0
    cpu_load_15: float = 0.0
    mem_total_gb: float = 0.0
    mem_avail_gb: float = 0.0
    mem_used_pct: float = 0.0


def _read_self_stat() -> dict:
    """Parse /proc/self/stat. Returns dict with key fields."""
    try:
        raw = SELF_STAT.read_text()
        fields = raw.split()
        # field 11 = utime (ticks), field 12 = stime (ticks)
        utime = int(fields[11])
        stime = int(fields[12])
        # field 23 = vsize (virtual memory), field 24 = rss (pages)
        vsize = int(fields[22]) if len(fields) > 22 else 0
        rss_pages = int(fields[23]) if len(fields) > 23 else 0
        # field 38 = processor (cpu core)
        processor = int(fields[38]) if len(fields) > 38 else 0
        # field 39 = rt_priority (thread count can be inferred from /proc/self/status)
        return {
            "utime": utime,
            "stime": stime,
            "vsize": vsize,
            "rss_pages": rss_pages,
            "processor": processor,
        }
    except (FileNotFoundError, IndexError, ValueError):
        return {"utime": 0, "stime": 0, "vsize": 0, "rss_pages": 0, "processor": 0}


def _read_self_io() -> dict:
    """Parse /proc/self/io for read/write bytes."""
    try:
        raw = SELF_IO.read_text()
        result = {}
        for line in raw.splitlines():
            key, _, val = line.partition(":")
            result[key.strip()] = int(val.strip())
        return result
    except (FileNotFoundError, ValueError):
        return {"read_bytes": 0, "write_bytes": 0}


def _read_thread_count() -> int:
    """Read thread count from /proc/self/status."""
    try:
        raw = SELF_STATUS.read_text()
        for line in raw.splitlines():
            if line.startswith("Threads:"):
                return int(line.split(":")[1].strip())
    except (FileNotFoundError, ValueError):
        pass
    return 0


def _clk_tck() -> int:
    """Get system clock ticks per second."""
    return os.sysconf(os.sysconf_names["SC_CLK_TCK"])


CLK_TCK = _clk_tck()
PAGE_SIZE = os.sysconf(os.sysconf_names["SC_PAGE_SIZE"])


def sample_process() -> dict:
    """Sample current process resource usage from /proc.

    Returns: Dict with cpu_ticks, rss_kb, read_bytes, write_bytes, threads.
    """
    stat = _read_self_stat()
    io = _read_self_io()
    return {
        "utime": stat["utime"],
        "stime": stat["stime"],
        "cpu_ticks": stat["utime"] + stat["stime"],
        "rss_kb": stat["rss_pages"] * PAGE_SIZE // 1024,
        "read_bytes": io.get("read_bytes", 0),
        "write_bytes": io.get("write_bytes", 0),
        "threads": _read_thread_count(),
    }


def sample_system() -> SystemSample:
    """Sample system-wide CPU load and memory from /proc.

    Returns: SystemSample dataclass.
    """
    load = (0.0, 0.0, 0.0)
    mem_total = 0
    mem_avail = 0
    try:
        load_raw = PROC_LOADAVG.read_text()
        parts = load_raw.split()
        load = (float(parts[0]), float(parts[1]), float(parts[2]))
    except (FileNotFoundError, IndexError, ValueError):
        pass
    try:
        mem_raw = PROC_MEMINFO.read_text()
        for line in mem_raw.splitlines():
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1])  # kB
            elif line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1])  # kB
    except (FileNotFoundError, ValueError):
        pass
    total_gb = mem_total / (1024 * 1024)
    avail_gb = mem_avail / (1024 * 1024)
    used_pct = ((mem_total - mem_avail) / mem_total * 100) if mem_total > 0 else 0
    return SystemSample(
        cpu_load_1=load[0],
        cpu_load_5=load[1],
        cpu_load_15=load[2],
        mem_total_gb=total_gb,
        mem_avail_gb=avail_gb,
        mem_used_pct=used_pct,
    )


class StepMonitor:
    """Tracks per-step resource deltas. Thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._steps: list[StepSnapshot] = []
        self._current: dict | None = None
        self._baseline: dict | None = None

    @contextmanager
    def measure(self, name: str):
        """Context manager to measure resource usage of a named step.

        Args:
            name: Step name for identification.
        """
        snap = self._start(name)
        try:
            yield snap
        finally:
            self._finish(snap)

    def _start(self, name: str) -> StepSnapshot:
        """Begin measurement for a step.

        Args:
            name: Step name.

        Returns: StepSnapshot being populated.
        """
        baseline = sample_process()
        t0 = time.monotonic()
        with self._lock:
            self._baseline = baseline
            self._current = StepSnapshot(name=name)
        snap = self._current
        snap.wall_s = t0
        return snap

    def _finish(self, snap: StepSnapshot):
        """Finalize measurement and record deltas.

        Args:
            snap: StepSnapshot from _start.
        """
        final = sample_process()
        t1 = time.monotonic()
        baseline = self._baseline
        with self._lock:
            if baseline:
                cpu_delta = (final["cpu_ticks"] - baseline["cpu_ticks"]) / CLK_TCK
                snap.cpu_s = cpu_delta
                snap.rss_kb_delta = final["rss_kb"] - baseline["rss_kb"]
                snap.read_bytes = final["read_bytes"] - baseline["read_bytes"]
                snap.write_bytes = final["write_bytes"] - baseline["write_bytes"]
                snap.thread_count = final["threads"]
            snap.wall_s = t1 - snap.wall_s
            self._steps.append(
                StepSnapshot(
                    **{
                        k: getattr(snap, k)
                        for k in [
                            "name",
                            "wall_s",
                            "cpu_s",
                            "rss_kb_delta",
                            "read_bytes",
                            "write_bytes",
                            "thread_count",
                        ]
                    }
                )
            )
            self._current = None
            self._baseline = None

    def steps(self) -> list[StepSnapshot]:
        """Return copy of all recorded step snapshots."""
        with self._lock:
            return list(self._steps)

    def clear(self):
        """Clear all recorded steps."""
        with self._lock:
            self._steps.clear()

    def latest(self) -> StepSnapshot | None:
        """Return most recent step snapshot, or None."""
        with self._lock:
            return self._steps[-1] if self._steps else None


# Global monitor
monitor = StepMonitor()


# --- OTEL-compatible export ---


@dataclass
class MetricPoint:
    """A single metric data point for OTEL export."""

    name: str
    value: float
    unit: str = "1"
    attributes: dict = field(default_factory=dict)


def export_otel_console(steps: list[StepSnapshot], system: SystemSample | None = None):
    """Print metrics in OTEL-compatible key=value format (for piping to OTEL collector)."""
    for s in steps:
        print(
            f"#otel step={s.name} wall_ms={s.wall_s * 1000:.0f} cpu_ms={s.cpu_s * 1000:.0f} rss_delta_kb={s.rss_kb_delta} read_bytes={s.read_bytes} write_bytes={s.write_bytes} threads={s.thread_count}"
        )
    if system:
        print(
            f"#otel system cpu_load_1={system.cpu_load_1:.2f} cpu_load_5={system.cpu_load_5:.2f} cpu_load_15={system.cpu_load_15:.2f} mem_total_gb={system.mem_total_gb:.2f} mem_avail_gb={system.mem_avail_gb:.2f} mem_used_pct={system.mem_used_pct:.1f}"
        )
