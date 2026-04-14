"""Disk usage collector."""

from __future__ import annotations

import os
import shutil
from typing import Any

from strata.collectors.base import Collector

# Mount points to check
_DEFAULT_MOUNTS = ["/", "/home", "/tmp", "/var"]


def _get_disk_usage(path: str) -> dict[str, Any] | None:
    """Get disk usage for a mount point."""
    try:
        usage = shutil.disk_usage(path)
        return {
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except (OSError, PermissionError):
        return None


class DiskCollector(Collector):
    """Collects disk usage information."""

    name = "disk"

    def collect(self) -> dict[str, Any]:
        result = {}
        seen_devs = set()

        # Read /proc/mounts for actual mount points
        mounts = _DEFAULT_MOUNTS[:]
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mount_point = parts[1]
                        if mount_point.startswith("/") and not mount_point.startswith(
                            ("/proc", "/sys", "/dev", "/run")
                        ):
                            if mount_point not in mounts:
                                mounts.append(mount_point)
        except (OSError, PermissionError):
            pass

        for mount in mounts:
            if os.path.isdir(mount):
                usage = _get_disk_usage(mount)
                if usage:
                    # Deduplicate by checking if it's a unique device
                    usage_key = (usage["total_gb"], usage["used_gb"])
                    if usage_key not in seen_devs:
                        seen_devs.add(usage_key)
                        result[mount] = usage

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if old is None:
            return f"+ {key}: mounted ({new.get('total_gb')} GB)"
        if new is None:
            return f"- {key}: unmounted"
        old_pct = old.get("percent_used", 0)
        new_pct = new.get("percent_used", 0)
        delta = new_pct - old_pct
        direction = "+" if delta > 0 else ""
        return f"  {key}: {old_pct}% -> {new_pct}% ({direction}{delta:.1f}%)"
