"""Unified TUI for 'both' mode — merges server + client panels."""

import re
import time
import traceback

from client_tui import ClientTUI
from monitor import monitor, sample_system
from rich.align import Align
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from state import server_state


class BothTUI:
    """Single TUI combining server stats and client progress."""

    def __init__(self, client_tui: ClientTUI):
        self.client_tui = client_tui
        self._running = False
        self._client_error: str | None = None
        self._client_done = False
        self._progress_bar = Progress(
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )
        self._progress_task = self._progress_bar.add_task("Idle", total=100)

    def set_client_error(self, error: str):
        self._client_error = error

    def set_client_done(self):
        self._client_done = True

    def run(self):
        self._running = True
        layout = self._build_layout()
        try:
            with Live(layout, refresh_per_second=4, screen=True) as _live:
                while self._running:
                    self._safe_update(layout, "header", self._render_header)
                    self._safe_update(layout, "body", self._render_client_status, "left", "status_panel")
                    self._safe_update(layout, "body", self._render_progress, "left", "progress_panel")
                    self._safe_update(layout, "body", self._render_steps, "left", "steps_panel")
                    self._safe_update(layout, "body", self._render_server_stats, "right", "server_stats")
                    self._safe_update(layout, "body", self._render_server_requests, "right", "server_requests")
                    self._safe_update(layout, "body", self._render_server_system, "right", "server_system")
                    self._safe_update(layout, "footer", self._render_footer)
                    time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    def _safe_update(self, layout, *path_and_fn):
        """Update a layout panel, catching and displaying any exception."""
        try:
            fn = path_and_fn[1]
            panel = fn()
            # Navigate layout path: layout["body"]["left"]["status_panel"]
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
                node.update(Panel(f"[red]{exc}[/red]\n{tb[-200:]}", border_style="red", title="Error"))
            except Exception:
                pass

    def stop(self):
        self._running = False

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
            Layout(name="status_panel", ratio=2),
            Layout(name="progress_panel", ratio=1),
            Layout(name="steps_panel", ratio=1),
        )
        layout["body"]["right"].split_column(
            Layout(name="server_stats", ratio=1),
            Layout(name="server_requests", ratio=2),
            Layout(name="server_system", ratio=1),
        )
        return layout

    def _render_header(self) -> Panel:
        srv_stats = server_state.snapshot()
        uptime = time.time() - srv_stats.start_time
        uptime_str = f"{int(uptime // 3600)}h{int((uptime % 3600) // 60)}m{int(uptime % 60)}s"

        with self.client_tui._lock:
            url = self.client_tui._server_url
            score = self.client_tui._power_score

        client_info = f" {url}" if url else ""
        score_info = f" | score={score:.1f}" if score else ""
        if self._client_error:
            client_info += " [red]ERROR[/red]"
        elif self._client_done:
            client_info += " [dim]done[/dim]"

        text = Text.assemble(
            ("ChunkDMesh", "bold cyan"),
            " | ",
            ("Server", "bold cyan"),
            (f" {uptime_str} | {srv_stats.request_count} reqs", ""),
            " | ",
            ("Client", "bold green"),
            (client_info, "cyan"),
            (score_info, "yellow"),
        )
        return Panel(text, style="black")

    def _render_client_status(self) -> Panel:
        ct = self.client_tui
        with ct._lock:
            status = ct._status
            detail = ct._status_detail
            region = ct._current_region
            batch = ct._batch_count

        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()
        table.add_row(
            "Status",
            Text(status, style="green" if status in ("done", "ready") else "yellow"),
        )
        if detail:
            table.add_row("Detail", detail)
        if region:
            table.add_row("Region", region)
        table.add_row("Batches", str(batch))
        if self._client_error:
            table.add_row("Error", Text(self._client_error[:80], style="red"))
        return Panel(table, title="Client Status", border_style="blue")

    def _render_progress(self) -> Panel:
        with self.client_tui._lock:
            progress = self.client_tui._current_progress
        pct = 0
        label = "Idle"
        if progress:
            mp = re.search(r"\((\d+(?:\.\d+)?)%\)", progress)
            if mp:
                pct = float(mp.group(1))
            mp2 = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", progress.replace(",", ""))
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
        return Panel(
            Align.center("\n".join([str(e) for e in elements])), title="Client Progress", border_style="yellow"
        )

    def _render_steps(self) -> Panel:
        steps = monitor.steps()
        if not steps:
            return Panel("No steps measured yet", title="Client Steps", border_style="dim")
        recent = steps[-6:]
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        table.add_column("Step", style="cyan")
        table.add_column("Wall", justify="right")
        table.add_column("CPU", justify="right")
        table.add_column("RSS", justify="right")
        for s in recent:
            wall = f"{s.wall_s * 1000:.0f}ms" if s.wall_s < 1 else f"{s.wall_s:.1f}s"
            cpu = f"{s.cpu_s * 1000:.0f}ms" if s.cpu_s < 1 else f"{s.cpu_s:.1f}s"
            rss = f"{s.rss_kb_delta // 1024}M" if abs(s.rss_kb_delta) > 1024 else f"{s.rss_kb_delta}K"
            table.add_row(s.name[:24], wall, cpu, rss)
        return Panel(table, title="Client Steps", border_style="green")

    def _render_server_stats(self) -> Panel:
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
        table.add_row("Clients", str(stats.active_clients))
        return Panel(table, title="Server Tasks", border_style="blue")

    def _render_server_requests(self) -> Panel:
        recent = server_state.recent_requests()
        if not recent:
            return Panel("No requests yet", title="Server Requests", border_style="dim")
        table = Table(box=None, padding=(0, 1), show_header=True, header_style="bold")
        table.add_column("Time", width=8)
        table.add_column("Path", style="cyan")
        table.add_column("Status", justify="right")
        for ts, path, status in recent[-12:]:
            t_str = time.strftime("%H:%M:%S", time.localtime(ts))
            status_style = "green" if status < 400 else "red"
            table.add_row(t_str, path[:50], Text(str(status), style=status_style))
        return Panel(table, title=f"Server Requests ({len(recent)})", border_style="magenta")

    def _render_server_system(self) -> Panel:
        sys_sample = sample_system()
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()
        table.add_row(
            "CPU Load", f"{sys_sample.cpu_load_1:.2f} / {sys_sample.cpu_load_5:.2f} / {sys_sample.cpu_load_15:.2f}"
        )
        table.add_row(
            "Memory", f"{sys_sample.mem_avail_gb:.1f}/{sys_sample.mem_total_gb:.1f} GB ({sys_sample.mem_used_pct:.0f}%)"
        )
        return Panel(table, title="System", border_style="cyan")

    def _render_footer(self) -> Panel:
        lines = []
        if self._client_error:
            lines.append(("", "❌", self._client_error[:100]))
        with self.client_tui._lock:
            client_lines = list(self.client_tui._log_buffer)
        lines.extend(client_lines[-3:])

        table = Table(box=None, padding=(0, 1), show_header=False)
        table.add_column("Time", style="dim", width=8)
        table.add_column("Icon", width=2)
        table.add_column("Message")
        for ts, icon, msg in lines[-4:]:
            table.add_row(ts, icon, msg[:120])
        if not lines:
            table.add_row("", "", "Waiting...")
        return Panel(table, title="Log", border_style="magenta")
