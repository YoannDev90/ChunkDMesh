"""Rich-based TUI for ChunkDMesh client."""

import threading
import time
from collections import deque

from monitor import StepSnapshot, SystemSample, monitor, sample_cpu_cores, sample_system
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text


class ClientTUI:
    """Rich-based TUI showing status, progress, logs, and system metrics."""

    MAX_LOG = 200

    def __init__(self):
        self.console = Console()
        self._log_buffer: deque = deque(maxlen=self.MAX_LOG)
        self._lock = threading.Lock()
        self._status = "initializing"
        self._status_detail = ""
        self._current_region = ""
        self._current_progress = ""
        self._batch_count = 0
        self._power_score = 0.0
        self._server_url = ""
        self._running = False
        self._log_offset = 0
        self._cpu_history: deque = deque(maxlen=60)
        self._mem_history: deque = deque(maxlen=60)
        self._latest_step: StepSnapshot | None = None
        self._system: SystemSample | None = None
        self._layout: Layout | None = None
        self._progress_bar = Progress(
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )
        self._progress_task = self._progress_bar.add_task("Idle", total=100)

    def set_status(self, status: str, detail: str = ""):
        """Update current status display."""
        with self._lock:
            self._status = status
            self._status_detail = detail

    def set_region(self, text: str):
        """Update current region label."""
        with self._lock:
            self._current_region = text

    def set_progress(self, text: str):
        """Update current progress text."""
        with self._lock:
            self._current_progress = text

    def set_batch_count(self, n: int):
        """Update batch count."""
        with self._lock:
            self._batch_count = n

    def set_power_score(self, s: float):
        """Update power score."""
        with self._lock:
            self._power_score = s

    def set_server_url(self, url: str):
        """Update server URL display."""
        with self._lock:
            self._server_url = url

    def log(self, icon: str, msg: str):
        """Append log entry to buffer.

        Args:
            icon: Emoji/icon prefix.
            msg: Log message text.
        """
        ts = time.strftime("%H:%M:%S")
        with self._lock:
            self._log_buffer.append((ts, icon, msg))

    def _build_layout(self) -> Layout:
        """Construct the TUI layout tree."""

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        layout["body"]["left"].split_column(
            Layout(name="status_panel", ratio=2),
            Layout(name="steps_panel", ratio=1),
        )
        layout["body"]["right"].split_column(
            Layout(name="progress_panel", ratio=2),
            Layout(name="log_panel", ratio=3),
        )
        return layout

    def _render_header(self) -> Panel:
        """Render top header panel with server URL and power score."""
        with self._lock:
            url = self._server_url
            score = self._power_score
        text = Text.assemble(
            ("ChunkDMesh Client", "bold green"),
            " | ",
            (f"Server: {url}", "cyan") if url else ("Server: --", "dim"),
            " | ",
            (f"Score: {score:.1f}", "yellow") if score else "",
        )
        return Panel(text, style="black")

    def _render_status(self) -> Panel:
        """Render status panel with current state, region, batch count."""
        with self._lock:
            status = self._status
            detail = self._status_detail
            region = self._current_region
            batch = self._batch_count
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()
        table.add_row(
            "Status", Text(status, style="green" if "done" in status.lower() or "ready" in status.lower() else "yellow")
        )
        if detail:
            table.add_row("Detail", detail)
        if region:
            table.add_row("Region", region)
        table.add_row("Batches", str(batch))
        return Panel(table, title="Status", border_style="blue")

    def _render_steps(self) -> Panel:
        """Render per-step metrics from monitor."""
        steps = monitor.steps()
        if not steps:
            return Panel("No steps measured yet", title="Per-Step Metrics", border_style="dim")
        recent = steps[-8:]
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("Step", style="cyan")
        table.add_column("Wall", justify="right")
        table.add_column("CPU", justify="right")
        table.add_column("RSSΔ", justify="right")
        for s in recent:
            wall = f"{s.wall_s * 1000:.0f}ms" if s.wall_s < 1 else f"{s.wall_s:.1f}s"
            cpu = f"{s.cpu_s * 1000:.0f}ms" if s.cpu_s < 1 else f"{s.cpu_s:.1f}s"
            rss = f"{s.rss_kb_delta // 1024}M" if abs(s.rss_kb_delta) > 1024 else f"{s.rss_kb_delta}K"
            table.add_row(s.name[:28], wall, cpu, rss)
        return Panel(table, title="Last Steps", border_style="green")

    def _render_progress(self) -> Panel:
        """Render progress bar with Chunky generation percentage."""
        import re as _re

        with self._lock:
            progress = self._current_progress
        pct = 0
        label = "Idle"
        if progress:
            mp = _re.search(r"\((\d+(?:\.\d+)?)%\)", progress)
            if mp:
                pct = float(mp.group(1))
            mp2 = _re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", progress.replace(",", ""))
            if mp2:
                done = int(mp2.group(1))
                total = int(mp2.group(2))
                if total > 0:
                    pct = done / total * 100
            label = "Chunky"
        self._progress_bar.update(self._progress_task, completed=pct, description=label)
        elements = [self._progress_bar]
        if progress:
            elements.append(Text(progress, style="yellow"))
        return Panel(Align.center("\n".join([str(e) for e in elements])), title="Progress", border_style="yellow")

    def _render_log(self) -> Panel:
        """Render log panel with scrollable log entries."""
        with self._lock:
            lines = list(self._log_buffer)
            offset = self._log_offset

        visible = 25
        if offset > 0:
            end = len(lines) - offset
            start = max(0, end - visible)
            shown = lines[start:end]
            scroll_info = f" ↑{offset}"
        else:
            shown = lines[-visible:]
            scroll_info = ""

        table = Table(box=None, padding=(0, 1), show_header=False)
        table.add_column("Time", style="dim", width=8)
        table.add_column("Icon", width=2)
        table.add_column("Message")
        for ts, icon, msg in shown:
            table.add_row(ts, icon, msg[:120])
        if not shown:
            table.add_row("", "", Text("Waiting for activity…", style="dim italic"))
        return Panel(table, title=f"Log{scroll_info}", border_style="magenta")

    def _render_system(self) -> Panel:
        """Render btop-style system resource panel with CPU cores, memory, and history."""
        sys = sample_system()
        cores = sample_cpu_cores()
        with self._lock:
            self._system = sys
            self._cpu_history.append((time.time(), sys.cpu_load_1))
            self._mem_history.append((time.time(), sys.mem_used_pct))
            cpu_hist = list(self._cpu_history)

        blocks = " ░▒▓█"
        bar_w = 20

        def _bar(pct: float, width: int = bar_w) -> str:
            filled = int(pct / 100 * width)
            return blocks[-1] * filled + blocks[1] * (width - filled)

        def _color_pct(pct: float) -> str:
            if pct < 50:
                return "green"
            if pct < 80:
                return "yellow"
            return "red"

        lines = []

        # CPU total bar
        cpu_pct = sys.cpu_total_pct if sys.cpu_total_pct > 0 else min(sys.cpu_load_1 * 25, 100)
        cpu_color = _color_pct(cpu_pct)
        lines.append(
            Text.assemble(
                (" CPU ", "bold cyan"),
                (_bar(cpu_pct), cpu_color),
                (f" {cpu_pct:5.1f}%", f"bold {cpu_color}"),
            )
        )

        # Per-core bars (compact, 2 per line)
        if cores:
            core_bar_w = 12
            for i in range(0, len(cores), 2):
                parts = []
                for j in range(2):
                    if i + j < len(cores):
                        c = cores[i + j]
                        filled = int(c / 100 * core_bar_w)
                        bar = blocks[-1] * filled + blocks[1] * (core_bar_w - filled)
                        col = _color_pct(c)
                        parts.append(
                            Text.assemble(
                                (f"cpu{i + j:>2} ", "dim"),
                                (bar, col),
                                (f" {c:4.0f}%", f"dim {col}"),
                            )
                        )
                line = Text()
                for p in parts:
                    line.append_text(p)
                    line.append("  ")
                lines.append(line)

        # Memory bar
        if sys.mem_total_gb > 0:
            mem_color = _color_pct(sys.mem_used_pct)
            used = sys.mem_used_gb
            bufs = sys.mem_buffers_gb
            cached = sys.mem_cached_gb
            lines.append(
                Text.assemble(
                    (" MEM ", "bold cyan"),
                    (_bar(sys.mem_used_pct), mem_color),
                    (f" {sys.mem_used_pct:5.1f}%", f"bold {mem_color}"),
                )
            )
            lines.append(
                Text.assemble(
                    ("     ", "dim"),
                    (f"{used:.1f}G", "white"),
                    (" used  ", "dim"),
                    (f"{bufs:.1f}G", "blue"),
                    (" buf  ", "dim"),
                    (f"{cached:.1f}G", "magenta"),
                    (" cache ", "dim"),
                    (f"/ {sys.mem_total_gb:.1f}G", "dim"),
                )
            )

        # CPU load
        lines.append(
            Text.assemble(
                ("Load ", "dim"),
                (f"{sys.cpu_load_1:.2f}", "cyan"),
                (" / ", "dim"),
                (f"{sys.cpu_load_5:.2f}", "cyan"),
                (" / ", "dim"),
                (f"{sys.cpu_load_15:.2f}", "cyan"),
            )
        )

        # Mini history sparkline (last 30 samples)
        if cpu_hist:
            recent = [v for _, v in cpu_hist[-30:]]
            spark_w = 30
            spark_blocks = " ▁▂▃▄▅▆▇█"
            spark = ""
            for v in recent[-spark_w:]:
                idx = min(int(v / 100 * (len(spark_blocks) - 1)), len(spark_blocks) - 1)
                spark += spark_blocks[idx]
            spark = spark.rjust(spark_w)
            lines.append(Text.assemble(("History ", "dim"), (spark, "cyan")))

        content = Group(*lines)
        return Panel(content, title=" SYSTEM ", border_style="cyan", expand=True)

    def _start_key_reader(self):
        """Start background thread to read arrow keys for log scrolling."""
        import os
        import select
        import sys

        def _reader():
            if not sys.stdin.isatty():
                return
            try:
                import termios
                import tty

                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setcbreak(fd)
                    while self._running:
                        if select.select([sys.stdin], [], [], 0.1)[0]:
                            ch = os.read(fd, 1)
                            if ch == b"\x1b" and select.select([sys.stdin], [], [], 0.05)[0]:
                                seq = os.read(fd, 2)
                                with self._lock:
                                    max_off = max(0, len(self._log_buffer) - 15)
                                    if seq == b"[A":
                                        self._log_offset = min(self._log_offset + 1, max_off)
                                    elif seq == b"[B":
                                        self._log_offset = max(self._log_offset - 1, 0)
                                    elif seq == b"[H":
                                        self._log_offset = max_off
                                    elif seq == b"[F":
                                        self._log_offset = 0
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except Exception:
                pass

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

    def run(self):
        """Start the TUI event loop with live display."""
        self._running = True
        self._start_key_reader()
        layout = self._build_layout()
        self._layout = layout

        # Disable mouse tracking at terminal level
        import sys as _sys

        _sys.stdout.write("\033[?1000l\033[?1002l\033[?1003l\033[?1006l")
        _sys.stdout.flush()

        try:
            with Live(layout, refresh_per_second=4, screen=True, console=self.console):
                while self._running:
                    with self._lock:
                        self._latest_step = monitor.latest()

                    layout["header"].update(self._render_header())
                    layout["footer"].update(self._render_system())
                    layout["body"]["left"]["status_panel"].update(self._render_status())
                    layout["body"]["left"]["steps_panel"].update(self._render_steps())
                    layout["body"]["right"]["progress_panel"].update(self._render_progress())
                    layout["body"]["right"]["log_panel"].update(self._render_log())
                    time.sleep(0.25)
        except KeyboardInterrupt:
            pass

    def stop(self):
        """Stop the TUI event loop."""
        self._running = False


# Background CLI output (when --bg is used)
tui = ClientTUI()


def log(icon: str, msg: str):
    """Log function used by main.py. Routes to TUI buffer and console."""
    tui.log(icon, msg)
    print(f"  {icon} {msg}")


def set_status(status: str, detail: str = ""):
    """Update TUI status from main module."""
    tui.set_status(status, detail)


def set_region(text: str):
    """Update TUI region display from main module."""
    tui.set_region(text)


def set_progress(text: str):
    """Update TUI progress from main module."""
    tui.set_progress(text)


def set_batch_count(n: int):
    """Update TUI batch count from main module."""
    tui.set_batch_count(n)


def set_power_score(s: float):
    """Update TUI power score from main module."""
    tui.set_power_score(s)


def set_server_url(url: str):
    """Update TUI server URL from main module."""
    tui.set_server_url(url)
