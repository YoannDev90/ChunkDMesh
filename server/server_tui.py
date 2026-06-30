"""Rich-based server TUI dashboard."""

import threading
import time

from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from state import server_state


class ServerTUI:
    def __init__(self):
        self._running = False
        self._stop_event = threading.Event()

    def _build_layout(self) -> Layout:
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
            Layout(name="stats_panel", ratio=1),
            Layout(name="clients_panel", ratio=1),
        )
        layout["body"]["right"].split_column(
            Layout(name="requests_panel", ratio=2),
            Layout(name="monitor_panel", ratio=1),
        )
        return layout

    def _render_header(self) -> Panel:
        stats = server_state.snapshot()
        uptime = time.time() - stats.start_time
        uptime_str = f"{int(uptime // 3600)}h{int((uptime % 3600) // 60)}m{int(uptime % 60)}s"
        text = Text.assemble(
            ("ChunkDMesh Server", "bold cyan"),
            " | ",
            (f"Uptime: {uptime_str}", "green"),
            " | ",
            (f"Requests: {stats.request_count}", "yellow"),
        )
        return Panel(text, style="black")

    def _render_stats(self) -> Panel:
        stats = server_state.snapshot()
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()
        table.add_row("Pending", str(stats.pending_tasks))
        table.add_row("Assigned", str(stats.assigned_tasks))
        table.add_row("Working", str(stats.working_tasks))
        table.add_row("Completed", str(stats.completed_tasks))
        table.add_row("Validated", str(stats.validated_tasks))
        table.add_row("Storage", f"{stats.total_storage_mb:.1f} MB")
        return Panel(table, title="Tasks & Storage", border_style="blue")

    def _render_clients(self) -> Panel:
        stats = server_state.snapshot()
        return Panel(
            Text(f"Active clients: {stats.active_clients}", style="bold green" if stats.active_clients > 0 else "dim"),
            title="Clients",
            border_style="green",
        )

    def _render_requests(self) -> Panel:
        recent = server_state.recent_requests()
        if not recent:
            return Panel("No requests yet", title="Recent Requests", border_style="dim")
        table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold")
        table.add_column("Time", width=8)
        table.add_column("Path", style="cyan")
        table.add_column("Status", justify="right")
        for ts, path, status in recent[-15:]:
            t_str = time.strftime("%H:%M:%S", time.localtime(ts))
            status_str = str(status)
            status_style = "green" if status < 400 else "red"
            table.add_row(t_str, path[:50], Text(status_str, style=status_style))
        return Panel(table, title=f"Recent Requests ({len(recent)})", border_style="magenta")

    def _render_monitor(self) -> Panel:
        from pathlib import Path

        try:
            proc_self = Path("/proc/self/status")
            rss = 0
            if proc_self.exists():
                for line in proc_self.read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        rss = int(line.split()[1]) // 1024
            load_path = Path("/proc/loadavg")
            load_str = "?"
            if load_path.exists():
                parts = load_path.read_text().split()[:3]
                load_str = " ".join(parts)
        except Exception:
            rss = 0
            load_str = "?"
        text = Text.assemble(
            (f"RSS: {rss} MB", "cyan"),
            " | ",
            (f"Load: {load_str}", "yellow"),
        )
        return Panel(text, title="Server Process", border_style="cyan")

    def run(self):
        self._running = True
        layout = self._build_layout()
        try:
            with Live(layout, refresh_per_second=4, screen=True) as _live:
                while self._running and not self._stop_event.is_set():
                    layout["header"].update(self._render_header())
                    layout["body"]["left"]["stats_panel"].update(self._render_stats())
                    layout["body"]["left"]["clients_panel"].update(self._render_clients())
                    layout["body"]["right"]["requests_panel"].update(self._render_requests())
                    layout["body"]["right"]["monitor_panel"].update(self._render_monitor())
                    time.sleep(0.25)
        except KeyboardInterrupt:
            pass

    def stop(self):
        self._running = False
        self._stop_event.set()
