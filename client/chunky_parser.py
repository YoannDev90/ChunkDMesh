"""Chunky progress parsing utilities."""

from __future__ import annotations

import re


def parse_chunky_progress(progress: str) -> dict:
    """Parse Chunky status output and return progress info."""
    info = {"done": 0, "total": 1024, "finished": False, "not_running": False}
    pl = progress.lower()

    m = re.search(r"(\d[\d,]*)\s*/\s*(\d[\d,]*)", progress.replace(",", ""))
    if m:
        info["done"] = int(m.group(1))
        info["total"] = int(m.group(2))
        return info

    m2 = re.search(r"(?:Processed|Finished|Generated)\s*:?\s*(\d[\d,]*)\s+chunks", progress.replace(",", ""))
    if m2:
        info["done"] = int(m2.group(1))
        mp = re.search(r"\((\d+(?:\.\d+)?)%\)", progress)
        if mp and info["done"] > 0:
            pct = float(mp.group(1))
            if pct > 0:
                info["total"] = min(int(info["done"] / (pct / 100)), 1024)
        return info

    m3 = re.search(r"(\d[\d,]*)\s+chunks", progress.replace(",", ""))
    if m3:
        info["done"] = int(m3.group(1))
        mp = re.search(r"\((\d+(?:\.\d+)?)%\)", progress)
        if mp and info["done"] > 0:
            pct = float(mp.group(1))
            if pct > 0:
                info["total"] = min(int(info["done"] / (pct / 100)), 1024)
        return info

    if "finished" in pl or "100%" in pl or "done" in pl:
        info["finished"] = True
    if "not running" in pl or "no tasks" in pl:
        info["not_running"] = True

    return info
