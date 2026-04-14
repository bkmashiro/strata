"""Running processes collector."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector


def _read_proc_stat(pid: int) -> dict[str, Any] | None:
    """Read process info from /proc/<pid>/stat and cmdline."""
    try:
        stat_path = Path(f"/proc/{pid}/stat")
        cmdline_path = Path(f"/proc/{pid}/cmdline")

        stat_content = stat_path.read_text()
        # Parse: pid (comm) state ...
        match = re.match(r"(\d+)\s+\((.+?)\)\s+(\S+)", stat_content)
        if not match:
            return None

        comm = match.group(2)
        state = match.group(3)

        cmdline = ""
        if cmdline_path.exists():
            raw = cmdline_path.read_bytes()
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()

        return {
            "pid": pid,
            "name": comm,
            "state": state,
            "cmdline": cmdline[:200],  # Truncate long command lines
        }
    except (PermissionError, FileNotFoundError, ProcessLookupError):
        return None


class ProcessCollector(Collector):
    """Collects running process information from /proc."""

    name = "processes"

    def collect(self) -> dict[str, Any]:
        result = {}
        try:
            pids = [int(d) for d in os.listdir("/proc") if d.isdigit()]
        except OSError:
            return result

        for pid in sorted(pids):
            info = _read_proc_stat(pid)
            if info and info["cmdline"]:
                # Key by name+cmdline hash for stability across restarts
                key = f"{info['name']}|{info['cmdline'][:80]}"
                result[key] = info
        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        name = key.split("|")[0]
        if old is None:
            pid = new.get("pid", "?")
            return f"+ {name} (PID {pid}): {new.get('cmdline', '')[:60]}"
        if new is None:
            pid = old.get("pid", "?")
            return f"- {name} (PID {pid}): stopped"
        return f"  {name}: state {old.get('state')} -> {new.get('state')}"
