"""Systemd service collector (Linux only)."""

from __future__ import annotations

import subprocess
from typing import Any

from strata.collectors.base import Collector


def _list_services(state: str) -> list[str]:
    """List systemd services in a given state."""
    try:
        proc = subprocess.run(
            [
                "systemctl", "list-units",
                "--type=service",
                f"--state={state}",
                "--no-pager",
                "--plain",
                "--no-legend",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return []

        services = []
        for line in proc.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if parts:
                # First column is the unit name
                service_name = parts[0]
                if service_name.endswith(".service"):
                    service_name = service_name[:-8]  # Strip .service suffix
                services.append(service_name)
        return services
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


class SystemdCollector(Collector):
    """Collects running and failed systemd services (Linux only)."""

    name = "systemd"

    @classmethod
    def is_available(cls) -> bool:
        """Check if systemctl is available."""
        try:
            proc = subprocess.run(
                ["systemctl", "--version"],
                capture_output=True,
                timeout=5,
            )
            return proc.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def collect(self) -> dict[str, Any]:
        result: dict[str, Any] = {}

        running = _list_services("running")
        if running:
            result["running"] = {svc: "running" for svc in sorted(running)}

        failed = _list_services("failed")
        if failed:
            result["failed"] = {svc: "failed" for svc in sorted(failed)}

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if key == "running":
            if old is None and isinstance(new, dict):
                return f"+ {len(new)} running services detected"
            if new is None and isinstance(old, dict):
                return f"- running services no longer reported"
            if isinstance(old, dict) and isinstance(new, dict):
                added = set(new.keys()) - set(old.keys())
                removed = set(old.keys()) - set(new.keys())
                parts = []
                if added:
                    parts.append(f"+{len(added)} started")
                if removed:
                    parts.append(f"-{len(removed)} stopped")
                return f"  running services: {', '.join(parts)}" if parts else "  running services: changed"
        if key == "failed":
            if old is None and isinstance(new, dict):
                return f"+ {len(new)} failed services detected"
            if new is None:
                return f"- no more failed services"
            if isinstance(old, dict) and isinstance(new, dict):
                added = set(new.keys()) - set(old.keys())
                removed = set(old.keys()) - set(new.keys())
                parts = []
                if added:
                    parts.append(f"+{len(added)} newly failed")
                if removed:
                    parts.append(f"-{len(removed)} recovered")
                return f"  failed services: {', '.join(parts)}" if parts else "  failed services: changed"
        if old is None:
            return f"+ {key}"
        if new is None:
            return f"- {key}"
        return f"  {key}: changed"
