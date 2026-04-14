"""System information collector."""

from __future__ import annotations

import os
import platform
import time
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector


def _get_uptime() -> float | None:
    """Get system uptime in seconds from /proc/uptime."""
    try:
        content = Path("/proc/uptime").read_text()
        return float(content.split()[0])
    except (OSError, ValueError):
        return None


def _get_load_average() -> tuple[float, ...] | None:
    """Get system load average."""
    try:
        return os.getloadavg()
    except OSError:
        return None


def _get_memory_info() -> dict[str, Any] | None:
    """Parse /proc/meminfo for memory stats."""
    try:
        info = {}
        content = Path("/proc/meminfo").read_text()
        for line in content.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                # Parse value in kB
                parts = val.strip().split()
                if parts:
                    try:
                        info[key.strip()] = int(parts[0])
                    except ValueError:
                        pass

        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        return {
            "total_mb": round(total / 1024, 1),
            "available_mb": round(available / 1024, 1),
            "used_mb": round((total - available) / 1024, 1),
            "percent_used": round((total - available) / total * 100, 1) if total else 0,
        }
    except (OSError, PermissionError):
        return None


class SystemCollector(Collector):
    """Collects system-level information."""

    name = "system"

    def collect(self) -> dict[str, Any]:
        result = {}

        result["hostname"] = platform.node()
        result["platform"] = platform.platform()
        result["python"] = platform.python_version()
        result["arch"] = platform.machine()

        uptime = _get_uptime()
        if uptime is not None:
            result["uptime_hours"] = round(uptime / 3600, 2)

        load = _get_load_average()
        if load is not None:
            result["load_avg"] = {
                "1min": round(load[0], 2),
                "5min": round(load[1], 2),
                "15min": round(load[2], 2),
            }

        mem = _get_memory_info()
        if mem is not None:
            result["memory"] = mem

        result["timestamp"] = time.time()

        return result
