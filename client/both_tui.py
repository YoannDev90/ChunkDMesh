"""Unified TUI for 'both' mode — 5 panels, no header/footer."""

import re
import threading
import time
import traceback
from collections import deque

from client_tui import ClientTUI
from monitor import monitor, sample_cpu_cores, sample_system
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

# Ordered step sequence for the checklist
_STEP_ORDER = [
    "wait_for_server",
    "power_score",
    "login",
    "fetch_config",
    "ensure_java",
    "setup_server",
    "download_mods",
    "install_loader",
    "server_start",
    "wait_ready",
    "server_restart",
    "rcon_connect",
    "fetch_task",
    "chunky_generation",
]

_STEP_LABELS = {
    "wait_for_server": "Connect to server",
    "power_score": "Benchmark power",
    "login": "Authenticate",
    "fetch_config": "Fetch config",
    "ensure_java": "Detect Java",
    "setup_server": "Setup MC server",
    "download_mods": "Download mods",
    "install_loader": "Install loader",
    "server_start": "Start MC server",
    "wait_ready": "Wait for server ready",
    "server_restart": "Restart server",
    "rcon_connect": "Connect RCON",
    "fetch_task": "Fetch task",
    "chunky_generation": "Chunky generation",
}


class BothTUI:
    """Unified TUI for 'both' mode — 5 panels, no header/footer."""

    def __init__(self, client_tui: ClientTUI, console_file=None):
        self.client_tui = client_tui
        self._running = False
        self._client_error: str | None = None
        self._client_done = False
        self._console = Console(file=console_file) if console_file else Console()
        self._progress = Progress(
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>5.1f}%"),
            TimeElapsedColumn(),
        )
        self._progress_task = self._progress.add_task("Idle", total=100)
        self._cpu_history: deque[float] = deque(maxlen=30)
        self._mem_history: deque[float] = deque(maxlen=30)
        self._log_offset = 0

    def set_client_error(self, error: str):
        """Set client error state for display."""
        self._client_error = error

    def set_client_done(self):
        """Mark client as done."""
        self._client_done = True

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
                                from state import server_state

                                client_logs = len(self.client_tui._log_buffer)
                                server_logs = len(server_state.recent_logs())
                                total = client_logs + server_logs
                                max_off = max(0, total - 10)
                                with self.client_tui._lock:
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
        """Start the unified TUI event loop."""
        self._running = True
        self._start_key_reader()
        layout = self._build_layout()

        # Disable mouse tracking at terminal level
        import sys as _sys

        _sys.stdout.write("\033[?1000l\033[?1002l\033[?1003l\033[?1006l")
        _sys.stdout.flush()

        try:
            with Live(layout, refresh_per_second=4, screen=True, console=self._console):
                while self._running:
                    self._safe_update(layout, "body", self._render_checklist, "left", "checklist")
                    self._safe_update(layout, "body", self._render_resources, "left", "resources")
                    self._safe_update(layout, "body", self._render_project, "right", "project")
                    self._safe_update(layout, "body", self._render_requests, "right", "requests")
                    self._safe_update(layout, "body", self._render_logs, "right", "logs")
                    time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    def _safe_update(self, layout, *path_and_fn):
        """Safely update a layout panel, catching and displaying errors."""
        try:
            fn = path_and_fn[1]
            panel = fn()
            node = layout
            for key in path_and_fn[2:]:
                node = node[key]
            node.update(panel)
        except Exception as exc:
            tb = traceback.format_exc()
            try:
                node = layout
                for key in path_and_fn[2:]:
                    node = node[key]
                node.update(Panel(Text(f"{exc}\n{tb[-200:]}", style="red"), title="Error", border_style="red"))
            except Exception:
                pass

    def stop(self):
        """Stop the unified TUI event loop."""
        self._running = False

    def _build_layout(self) -> Layout:
        """Construct the 5-panel layout tree for both mode."""
        layout = Layout()
        layout.split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        layout["left"].split_column(
            Layout(name="checklist", ratio=3),
            Layout(name="resources", ratio=2),
        )
        layout["right"].split_column(
            Layout(name="project", ratio=1),
            Layout(name="requests", ratio=2),
            Layout(name="logs", ratio=3),
        )
        return layout

    # ── Left: Checklist + Progress ────────────────────────────

    def _render_checklist(self) -> Panel:
        """Render client checklist with step completion and progress bar."""
        ct = self.client_tui
        with ct._lock:
            status = ct._status
            detail = ct._status_detail
            progress = ct._current_progress

        # Determine which steps are done
        done_steps = set()
        for s in monitor.steps():
            done_steps.add(s.name)

        # Current step from status
        current_map = {
            "connecting": "wait_for_server",
            "connected": "power_score",
            "login": "login",
            "config": "fetch_config",
            "java": "ensure_java",
            "setup": "setup_server",
            "mods": "download_mods",
            "installing_loader": "install_loader",
            "launching": "server_start",
            "ready": "rcon_connect",
            "generating": "chunky_generation",
            "idle": "fetch_task",
        }
        current_step = current_map.get(status, "")

        # Build checklist
        lines = Table(box=None, padding=(0, 1), show_header=False, expand=True)
        lines.add_column(width=2, justify="center")
        lines.add_column(ratio=1)

        for step_key in _STEP_ORDER:
            label = _STEP_LABELS.get(step_key, step_key)
            if step_key in done_steps:
                lines.add_row(Text("✓", style="bold green"), Text(label, style="green"))
            elif step_key == current_step:
                lines.add_row(Text("►", style="bold cyan"), Text(label, style="bold cyan"))
            else:
                lines.add_row(Text("○", style="dim"), Text(label, style="dim"))

        # Progress bar
        pct = 0.0
        if progress:
            mp = re.search(r"\((\d+(?:\.\d+)?)%\)", progress)
            if mp:
                pct = float(mp.group(1))
            else:
                mp2 = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", progress.replace(",", ""))
                if mp2:
                    done_n = int(mp2.group(1))
                    total_n = int(mp2.group(2))
                    if total_n > 0:
                        pct = done_n / total_n * 100

        label = "Chunky" if progress else "Idle"
        self._progress.update(self._progress_task, completed=pct, description=label)

        # Status line
        status_text = Text()
        if self._client_error:
            status_text.append("✗ ", style="bold red")
            status_text.append(self._client_error[:60], style="red")
        elif self._client_done:
            status_text.append("✓ Done", style="bold green")
        elif detail:
            status_text.append(status, style="cyan")
            status_text.append(f" — {detail}", style="dim")
        else:
            status_text.append(status, style="cyan")

        content = Group(lines, Text(), self._progress, Text(), status_text)
        return Panel(content, title=" CLIENT ", border_style="blue", expand=True)

    # ── Left: Resource Monitor ────────────────────────────────

    def _render_resources(self) -> Panel:
        """Render btop-style resource panel with CPU cores, memory, and history."""
        sys = sample_system()
        cores = sample_cpu_cores()
        self._cpu_history.append(sys.cpu_load_1)
        self._mem_history.append(sys.mem_used_pct)

        blocks = " ░▒▓█"
        bar_w = 18

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
                ("CPU  ", "bold cyan"),
                (_bar(cpu_pct), cpu_color),
                (f" {cpu_pct:5.1f}%", f"bold {cpu_color}"),
                (f"  {sys.cpu_load_1:.2f}/{sys.cpu_load_5:.2f}/{sys.cpu_load_15:.2f}", "dim"),
            )
        )

        # Per-core bars (compact)
        if cores:
            core_bar_w = 10
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
                                (f"c{i + j:<2}", "dim"),
                                (bar, col),
                                (f"{c:3.0f}%", f"dim {col}"),
                            )
                        )
                line = Text()
                for p in parts:
                    line.append_text(p)
                    line.append(" ")
                lines.append(line)

        # Memory bar
        if sys.mem_total_gb > 0:
            mem_color = _color_pct(sys.mem_used_pct)
            lines.append(
                Text.assemble(
                    ("MEM  ", "bold cyan"),
                    (_bar(sys.mem_used_pct), mem_color),
                    (f" {sys.mem_used_pct:5.1f}%", f"bold {mem_color}"),
                    (f"  {sys.mem_used_gb:.1f}/{sys.mem_total_gb:.1f}G", "dim"),
                )
            )
            lines.append(
                Text.assemble(
                    ("     ", "dim"),
                    (f"buf:{sys.mem_buffers_gb:.1f}G", "blue"),
                    ("  ", "dim"),
                    (f"cache:{sys.mem_cached_gb:.1f}G", "magenta"),
                )
            )

        # History sparkline
        if self._cpu_history:
            spark_blocks = " ▁▂▃▄▅▆▇█"
            recent = list(self._cpu_history)[-30:]
            spark = ""
            for v in recent:
                idx = min(int(v / 100 * (len(spark_blocks) - 1)), len(spark_blocks) - 1)
                spark += spark_blocks[idx]
            lines.append(Text.assemble(("Hist  ", "dim"), (spark.rjust(30), "cyan")))

        content = Group(*lines)
        return Panel(content, title=" RESOURCES ", border_style="cyan", expand=True)

    @staticmethod
    def _sparkline(data: deque, max_val: float, width: int = 40) -> str:
        """Render a unicode sparkline from recent data samples.

        Args:
            data: Time-series values.
            max_val: Maximum value for scaling.
            width: Character width of output.

        Returns: Sparkline string.
        """
        if not data:
            return "░" * width
        blocks = " ▁▂▃▄▅▆▇█"
        # Map last `width` samples to block chars
        recent = list(data)[-width:]
        result = []
        for v in recent:
            idx = min(int(v / max_val * (len(blocks) - 1)), len(blocks) - 1)
            result.append(blocks[idx])
        # Pad to width
        while len(result) < width:
            result.insert(0, " ")
        return "".join(result)

    # ── Right: Project Info ───────────────────────────────────

    def _render_project(self) -> Panel:
        """Render project info panel with world config, uptime, and task progress."""
        from state import server_state

        stats = server_state.snapshot()
        config = stats.world_config

        table = Table.grid(padding=(0, 1), expand=True)
        table.add_column(width=12, style="bold")
        table.add_column()

        # Uptime
        uptime = time.time() - stats.start_time
        h, rem = divmod(int(uptime), 3600)
        m, s = divmod(rem, 60)
        table.add_row("Uptime", Text(f"{h:02d}:{m:02d}:{s:02d}", style="dim"))

        # World config
        if config:
            table.add_row("World", Text(config.get("world_name", "?"), style="bold white"))
            table.add_row("Seed", Text(str(config.get("seed", "?")), style="cyan"))
            table.add_row("Dimension", Text(config.get("dimension", "?"), style="cyan"))
            table.add_row("Shape", Text(config.get("shape", "?"), style="cyan"))
            table.add_row(
                "Loader",
                Text(f"{config.get('minecraft_loader', '?')} {config.get('minecraft_version', '?')}", style="cyan"),
            )
            table.add_row("Radius", Text(f"{config.get('radius', '?')} chunks", style="cyan"))
        else:
            table.add_row("World", Text("loading…", style="dim"))

        # Clients
        client_style = "bold green" if stats.active_clients > 0 else "dim"
        table.add_row("Clients", Text(str(stats.active_clients), style=client_style))

        # Tasks
        total = max(
            stats.pending_tasks
            + stats.assigned_tasks
            + stats.working_tasks
            + stats.completed_tasks
            + stats.validated_tasks,
            1,
        )
        pct_done = (stats.completed_tasks + stats.validated_tasks) / total * 100
        bar = "█" * int(pct_done / 100 * 15) + "░" * (15 - int(pct_done / 100 * 15))
        table.add_row(
            "Progress",
            Text(f"{bar} {stats.completed_tasks + stats.validated_tasks}/{total}", style="green"),
        )

        return Panel(table, title=" PROJECT ", border_style="bright_cyan", expand=True)

    # ── Right: API Requests ───────────────────────────────────

    def _render_requests(self) -> Panel:
        """Render recent API requests panel."""
        from state import server_state

        recent = server_state.recent_requests()
        if not recent:
            return Panel(Text("  No requests yet", style="dim italic"), title=" REQUESTS ", border_style="dim")

        table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1), expand=True)
        table.add_column("Time", width=8, style="dim")
        table.add_column("Path", style="cyan", ratio=3)
        table.add_column("Status", justify="right", ratio=1)

        for ts, path, status in recent[-20:]:
            t_str = time.strftime("%H:%M:%S", time.localtime(ts))
            s_style = "green" if status < 300 else "yellow" if status < 400 else "red" if status < 500 else "bold red"
            table.add_row(t_str, path[:50], Text(str(status), style=s_style))

        return Panel(table, title=f" REQUESTS [{len(recent)}] ", border_style="magenta")

    # ── Right: Live Logs ──────────────────────────────────────

    def _render_logs(self) -> Panel:
        """Render merged server and client log entries with scroll support."""
        from state import server_state

        logs = server_state.recent_logs()

        # Also include client logs
        with self.client_tui._lock:
            client_lines = list(self.client_tui._log_buffer)

        # Merge: server logs first, then client logs
        all_lines = []
        for ts, icon, msg in logs:
            all_lines.append((ts, icon, msg))
        for ts, icon, msg in client_lines:
            all_lines.append((ts, icon, msg))

        # Apply scroll offset
        visible = 20
        with self.client_tui._lock:
            offset = self._log_offset
        if offset > 0:
            end = len(all_lines) - offset
            start = max(0, end - visible)
            shown = all_lines[start:end]
            scroll_info = f" ↑{offset}"
        else:
            shown = all_lines[-visible:]
            scroll_info = ""

        table = Table(box=None, padding=(0, 1), show_header=False, expand=True)
        table.add_column("Time", style="dim", width=8)
        table.add_column("Icon", width=2)
        table.add_column("Message", overflow="ellipsis")

        for ts, icon, msg in shown:
            table.add_row(ts, icon, msg[:100])
        if not shown:
            table.add_row("", "", Text("Waiting for activity…", style="dim italic"))

        return Panel(table, title=f" LOGS{scroll_info} ", border_style="magenta")
