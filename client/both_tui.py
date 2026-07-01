"""Unified TUI for 'both' mode — merges server + client panels."""

import re
import time
import traceback

from client_tui import ClientTUI
from monitor import monitor, sample_system
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text


def _status_dot(status: str) -> Text:
    t = Text()
    if status in ("done", "ready", "connected"):
        t.append("● ", style="bold green")
        t.append(status, style="green")
    elif status in ("initializing", "connecting", "login"):
        t.append("● ", style="bold yellow")
        t.append(status, style="yellow")
    elif status in ("error",):
        t.append("● ", style="bold red")
        t.append(status, style="red")
    else:
        t.append("● ", style="bold cyan")
        t.append(status, style="cyan")
    return t


class BothTUI:
    """Single TUI combining server stats and client progress."""

    def __init__(self, client_tui: ClientTUI, console_file=None):
        self.client_tui = client_tui
        self._running = False
        self._client_error: str | None = None
        self._client_done = False
        self._console = Console(file=console_file) if console_file else Console()
        self._progress = Progress(
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
        )
        self._progress_task = self._progress.add_task("Idle", total=100)

    def set_client_error(self, error: str):
        self._client_error = error

    def set_client_done(self):
        self._client_done = True

    def run(self):
        self._running = True
        layout = self._build_layout()
        try:
            with Live(layout, refresh_per_second=4, screen=True, console=self._console):
                while self._running:
                    self._safe_update(layout, "header", self._render_header)
                    self._safe_update(layout, "body", self._render_client, "left", "client_panel")
                    self._safe_update(layout, "body", self._render_steps, "left", "steps_panel")
                    self._safe_update(layout, "body", self._render_server_tasks, "right", "server_panel")
                    self._safe_update(layout, "body", self._render_server_requests, "right", "requests_panel")
                    self._safe_update(layout, "body", self._render_system, "right", "system_panel")
                    self._safe_update(layout, "footer", self._render_footer)
                    time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False

    def _safe_update(self, layout, *path_and_fn):
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
        self._running = False

    def _build_layout(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=5),
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right"),
        )
        layout["body"]["left"].split_column(
            Layout(name="client_panel", ratio=3),
            Layout(name="steps_panel", ratio=2),
        )
        layout["body"]["right"].split_column(
            Layout(name="server_panel", ratio=2),
            Layout(name="requests_panel", ratio=3),
            Layout(name="system_panel", ratio=1),
        )
        return layout

    # ── Header ────────────────────────────────────────────────

    def _render_header(self) -> Panel:
        srv = self._srv_stats()

        uptime = time.time() - srv.start_time
        h, rem = divmod(int(uptime), 3600)
        m, s = divmod(rem, 60)
        uptime_str = f"{h:02d}:{m:02d}:{s:02d}"

        with self.client_tui._lock:
            score = self.client_tui._power_score

        left = Text()
        left.append(" ◆ ", style="bold cyan")
        left.append("ChunkDMesh", style="bold white")

        center = Text()
        center.append(f" ⏱ {uptime_str}", style="dim")
        center.append(f" │ {srv.request_count} reqs", style="dim")
        center.append(f" │ {srv.active_clients} clients", style="dim")

        right = Text()
        if self._client_error:
            right.append(" CLIENT ", style="bold white on red")
            right.append(" ✗ ", style="red")
        elif self._client_done:
            right.append(" CLIENT ", style="bold white on green")
            right.append(" ✓ ", style="green")
        else:
            right.append(" CLIENT ", style="bold white on blue")
            right.append(" … ", style="cyan")
        if score:
            right.append(f" {score:.1f}", style="yellow")

        return Panel(Group(left, center, right), style="dim on grey11", border_style="bright_cyan")

    # ── Client panel (status + progress) ──────────────────────

    def _render_client(self) -> Panel:
        ct = self.client_tui
        with ct._lock:
            status = ct._status
            detail = ct._status_detail
            region = ct._current_region
            batch = ct._batch_count
            progress = ct._current_progress

        # Status
        status_table = Table.grid(padding=(0, 1), expand=True)
        status_table.add_column(width=8, style="bold")
        status_table.add_column()
        status_table.add_row("Status", _status_dot(status))
        if detail:
            status_table.add_row("Detail", Text(detail, style="dim"))
        if region:
            status_table.add_row("Region", Text(region, style="cyan"))
        status_table.add_row("Batches", Text(str(batch), style="bold"))

        # Progress bar
        pct = 0.0
        progress_text = ""
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
                    progress_text = f"{done:,} / {total:,}"

        label = "Chunky" if progress else "Idle"
        self._progress.update(self._progress_task, completed=pct, description=label)

        progress_table = Table.grid(padding=(0, 1), expand=True)
        progress_table.add_column(width=8, style="bold")
        progress_table.add_column()
        progress_table.add_row("Progress", self._progress)
        if progress_text:
            progress_table.add_row("Chunks", Text(progress_text, style="dim"))

        content = Group(status_table, Text(), progress_table)
        return Panel(content, title=" CLIENT ", border_style="blue", expand=True)

    # ── Steps panel ───────────────────────────────────────────

    def _render_steps(self) -> Panel:
        steps = monitor.steps()
        if not steps:
            return Panel(
                Text("  Waiting for measurements…", style="dim italic"),
                title=" STEPS ",
                border_style="dim",
            )

        table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1), expand=True)
        table.add_column("Step", style="white", ratio=3)
        table.add_column("Wall", justify="right", ratio=1)
        table.add_column("CPU", justify="right", ratio=1)
        table.add_column("RSS Δ", justify="right", ratio=1)

        for s in steps[-8:]:
            wall_s = s.wall_s
            cpu_s = s.cpu_s
            rss = s.rss_kb_delta

            wall_str = f"{wall_s * 1000:.0f}ms" if wall_s < 1 else f"{wall_s:.1f}s"
            cpu_str = f"{cpu_s * 1000:.0f}ms" if cpu_s < 1 else f"{cpu_s:.1f}s"

            wall_style = "red" if wall_s > 5 else "yellow" if wall_s > 1 else "green"
            cpu_style = "red" if cpu_s > 3 else "yellow" if cpu_s > 0.5 else "green"
            rss_style = "red" if abs(rss) > 50_000 else "yellow" if abs(rss) > 10_000 else "dim"
            rss_str = f"{rss // 1024:+d}M" if abs(rss) > 1024 else f"{rss:+d}K"

            table.add_row(
                Text(s.name[:30], style="white"),
                Text(wall_str, style=wall_style),
                Text(cpu_str, style=cpu_style),
                Text(rss_str, style=rss_style),
            )

        return Panel(table, title=" STEPS ", border_style="green")

    # ── Server tasks panel ────────────────────────────────────

    def _render_server_tasks(self) -> Panel:
        stats = self._srv_stats()
        total = max(
            stats.pending_tasks
            + stats.assigned_tasks
            + stats.working_tasks
            + stats.completed_tasks
            + stats.validated_tasks,
            1,
        )

        def _row(label: str, count: int, color: str) -> Text:
            pct = count / total * 100
            filled = int(pct / 100 * 15)
            bar = "█" * filled + "░" * (15 - filled)
            return Text(f"  {bar}  {count:>4}", style=color)

        rows = Group(
            _make_row("Pending", stats.pending_tasks, "cyan"),
            _make_row("Assigned", stats.assigned_tasks, "yellow"),
            _make_row("Working", stats.working_tasks, "green"),
            _make_row("Completed", stats.completed_tasks, "bright_green"),
            _make_row("Validated", stats.validated_tasks, "bold green"),
        )

        storage = Text(f"\n  💾 {stats.total_storage_mb:.1f} MB  │  👥 {stats.active_clients} clients", style="dim")

        return Panel(Group(rows, storage), title=" SERVER ", border_style="blue")

    # ── Server requests panel ─────────────────────────────────

    def _render_server_requests(self) -> Panel:
        recent = self._srv_recent()
        if not recent:
            return Panel(Text("  No requests yet", style="dim italic"), title=" REQUESTS ", border_style="dim")

        table = Table(show_header=True, header_style="bold magenta", box=None, padding=(0, 1), expand=True)
        table.add_column("Time", width=8, style="dim")
        table.add_column("Path", style="cyan", ratio=3)
        table.add_column("Status", justify="right", ratio=1)

        for ts, path, status in recent[-14:]:
            t_str = time.strftime("%H:%M:%S", time.localtime(ts))
            s_style = "green" if status < 300 else "yellow" if status < 400 else "red" if status < 500 else "bold red"
            table.add_row(t_str, path[:50], Text(str(status), style=s_style))

        return Panel(table, title=f" REQUESTS [{len(recent)}] ", border_style="magenta")

    # ── System panel ──────────────────────────────────────────

    def _render_system(self) -> Panel:
        sys = sample_system()

        table = Table.grid(padding=(0, 2), expand=True)
        table.add_column(width=12, style="bold")
        table.add_column()

        cpu_color = "green" if sys.cpu_load_1 < 2 else "yellow" if sys.cpu_load_1 < 4 else "red"
        table.add_row(
            "CPU 1/5/15",
            Text(f"{sys.cpu_load_1:.1f}  {sys.cpu_load_5:.1f}  {sys.cpu_load_15:.1f}", style=cpu_color),
        )

        mem_color = "green" if sys.mem_used_pct < 60 else "yellow" if sys.mem_used_pct < 85 else "red"
        filled = int(sys.mem_used_pct / 100 * 20)
        mem_bar = "█" * filled + "░" * (20 - filled)
        table.add_row(
            "Memory",
            Text(
                f"{mem_bar} {sys.mem_used_pct:.0f}%  ({sys.mem_avail_gb:.1f}/{sys.mem_total_gb:.1f} GB)",
                style=mem_color,
            ),
        )

        return Panel(table, title=" SYSTEM ", border_style="cyan")

    # ── Footer (log) ──────────────────────────────────────────

    def _render_footer(self) -> Panel:
        lines = []
        if self._client_error:
            lines.append(("", "✗", self._client_error[:120]))
        with self.client_tui._lock:
            client_lines = list(self.client_tui._log_buffer)
        lines.extend(client_lines[-4:])

        table = Table(box=None, padding=(0, 1), show_header=False, expand=True)
        table.add_column("Time", style="dim", width=8)
        table.add_column("Icon", width=2)
        table.add_column("Message", overflow="ellipsis")

        for ts, icon, msg in lines[-4:]:
            table.add_row(ts, icon, msg[:120])
        if not lines:
            table.add_row("", "", Text("Initializing…", style="dim italic"))

        return Panel(table, title=" LOG ", border_style="magenta")

    # ── Helpers ───────────────────────────────────────────────

    def _srv_stats(self):
        from state import server_state

        return server_state.snapshot()

    def _srv_recent(self):
        from state import server_state

        return server_state.recent_requests()


def _make_row(label: str, count: int, color: str) -> Table:
    """Helper to build a server task row with bar."""
    t = Table.grid(padding=(0, 1), expand=True)
    t.add_column(width=10, style="bold")
    t.add_column()
    t.add_row(label, Text(f"{count}", style=color))
    return t
