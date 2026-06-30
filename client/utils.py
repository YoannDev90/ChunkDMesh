"""Resource monitoring using /proc (no psutil)."""

import contextlib
import os
from pathlib import Path

PROC = Path("/proc")


class ResourceReportFormat:
    DETAILED = "detailed"
    VALUE = "value"


def _read_proc(path: str) -> str:
    try:
        return (PROC / path).read_text()
    except (FileNotFoundError, PermissionError):
        return ""


def get_available_resources_averaged(print_output=False, return_format=ResourceReportFormat.DETAILED):
    """Resources via /proc (Linux only). CPU frequency, load, RAM."""

    num_cores = os.cpu_count() or 1

    # CPU load from /proc/loadavg
    load_data = _read_proc("loadavg").split()
    load_avg = (float(load_data[0]), float(load_data[1]), float(load_data[2])) if len(load_data) >= 3 else (0, 0, 0)

    # CPU frequency from /proc/cpuinfo
    freq_current = 0.0
    freq_max = 0.0
    cpuinfo = _read_proc("cpuinfo")
    freqs = []
    for line in cpuinfo.splitlines():
        if line.startswith("cpu MHz"):
            with contextlib.suppress((IndexError, ValueError)):
                freqs.append(float(line.split(":")[1].strip()))
    if freqs:
        freq_current = sum(freqs) / len(freqs) / 1000  # MHz -> GHz
        freq_max = max(freqs) / 1000
    else:
        # fallback: estimate from scaling governor
        scaling = _read_proc("cpu/0/cpufreq/scaling_cur_freq").strip()
        if scaling:
            try:
                freq_current = int(scaling) / 1_000_000
            except ValueError:
                freq_current = 2.0
        max_scaling = _read_proc("cpu/0/cpufreq/scaling_max_freq").strip()
        if max_scaling:
            try:
                freq_max = int(max_scaling) / 1_000_000
            except ValueError:
                freq_max = freq_current
        if not freq_current:
            freq_current = 2.0
        if not freq_max:
            freq_max = freq_current

    # RAM from /proc/meminfo
    mem_total = 0
    mem_available = 0
    for line in _read_proc("meminfo").splitlines():
        if line.startswith("MemTotal:"):
            mem_total = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            mem_available = int(line.split()[1])
    ram_total = mem_total / (1024 * 1024) if mem_total else 16.0
    ram_available = mem_available / (1024 * 1024) if mem_available else 8.0
    ram_used_pct = ((mem_total - mem_available) / mem_total * 100) if mem_total > 0 else 50

    cpu_used_pct = min(100, (load_avg[1] / num_cores) * 100) if num_cores > 0 else 50
    cpu_available_pct = 100 - cpu_used_pct
    ram_available_pct = 100 - ram_used_pct

    cpu_power = freq_current * num_cores * (cpu_available_pct / 100)
    ram_power = ram_available * (ram_available_pct / 100)
    power_available = cpu_power * (ram_power / ram_total) if ram_total > 0 else 0

    if print_output:
        print("=== CPU ===")
        print(f"Load average (1/5/15 min): {load_avg[0]:.2f} / {load_avg[1]:.2f} / {load_avg[2]:.2f}")
        print(f"Frequency: {freq_current:.1f} GHz / {freq_max:.1f} GHz (max)")
        print(f"Cores: {num_cores}")
        print(f"Usage (avg 5min): {cpu_used_pct:.1f}%")
        print(f"CPU available: {cpu_available_pct:.1f}%")
        print("\n=== RAM ===")
        print(f"Total: {ram_total:.1f} Go")
        print(f"Available: {ram_available:.1f} Go")
        print(f"Usage: {ram_used_pct:.1f}%")
        print(f"RAM available: {ram_available_pct:.1f}%")
        print("\n=== SCORE ===")
        print(f"Available CPU power: {cpu_power:.2f}")
        print(f"Available RAM power: {ram_power:.2f} Go")
        print(f"Total power score: {power_available:.2f}")

    infos = {
        'load_avg_5min': load_avg[1],
        'cpu_freq_ghz': freq_current,
        'cpu_available_pct': cpu_available_pct,
        'cpu_power': cpu_power,
        'ram_available_gb': ram_available,
        'ram_available_pct': ram_available_pct,
        'ram_power': ram_power,
        'power_score': power_available
    } if return_format == ResourceReportFormat.DETAILED else power_available

    return infos
