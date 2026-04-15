"""Crontab entries collector."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector


def _get_user_crontab() -> list[dict[str, str]]:
    """Get current user's crontab entries."""
    try:
        proc = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return []

        entries = []
        for line in proc.stdout.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Try to parse cron schedule and command
            parts = line.split(None, 5)
            if len(parts) >= 6:
                entries.append({
                    "schedule": " ".join(parts[:5]),
                    "command": parts[5],
                    "source": "user_crontab",
                })
            elif line.startswith("@"):
                # Handle @reboot, @daily etc.
                parts = line.split(None, 1)
                if len(parts) == 2:
                    entries.append({
                        "schedule": parts[0],
                        "command": parts[1],
                        "source": "user_crontab",
                    })
        return entries
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def _get_system_cron_entries() -> list[dict[str, str]]:
    """Get entries from /etc/cron.d/ and other system cron directories."""
    entries = []
    cron_dirs = [
        "/etc/cron.d",
        "/etc/cron.daily",
        "/etc/cron.hourly",
        "/etc/cron.weekly",
        "/etc/cron.monthly",
    ]

    for cron_dir in cron_dirs:
        dir_path = Path(cron_dir)
        if not dir_path.is_dir():
            continue
        try:
            for entry in sorted(dir_path.iterdir()):
                if not entry.is_file():
                    continue
                try:
                    content = entry.read_text(errors="replace")
                    # For daily/hourly/weekly/monthly, just note the script name
                    dir_name = dir_path.name
                    if dir_name in ("cron.daily", "cron.hourly", "cron.weekly", "cron.monthly"):
                        entries.append({
                            "schedule": dir_name.replace("cron.", "@"),
                            "command": entry.name,
                            "source": str(cron_dir),
                        })
                    else:
                        # /etc/cron.d/ files: parse like crontab
                        for line in content.split("\n"):
                            line = line.strip()
                            if not line or line.startswith("#"):
                                continue
                            parts = line.split(None, 6)
                            if len(parts) >= 7:
                                entries.append({
                                    "schedule": " ".join(parts[:5]),
                                    "user": parts[5],
                                    "command": parts[6],
                                    "source": str(entry),
                                })
                except (OSError, PermissionError):
                    continue
        except (PermissionError, OSError):
            continue

    return entries


class CrontabCollector(Collector):
    """Collects crontab entries for the current user and system cron."""

    name = "crontab"

    def collect(self) -> dict[str, Any]:
        result: dict[str, Any] = {}

        user_entries = _get_user_crontab()
        if user_entries:
            for i, entry in enumerate(user_entries):
                key = f"user:{i}:{entry.get('command', 'unknown')[:60]}"
                result[key] = entry

        system_entries = _get_system_cron_entries()
        if system_entries:
            for i, entry in enumerate(system_entries):
                key = f"system:{entry.get('source', '')}:{entry.get('command', 'unknown')[:60]}"
                result[key] = entry

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if old is None:
            schedule = new.get("schedule", "?")
            command = new.get("command", "?")[:50]
            return f"+ cron: {schedule} {command}"
        if new is None:
            schedule = old.get("schedule", "?")
            command = old.get("command", "?")[:50]
            return f"- cron: {schedule} {command}"
        return f"  cron: schedule/command changed for {key}"
