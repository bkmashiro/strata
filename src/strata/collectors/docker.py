"""Docker containers collector."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from strata.collectors.base import Collector


class DockerCollector(Collector):
    """Collects running Docker container information."""

    name = "docker"

    @classmethod
    def is_available(cls) -> bool:
        """Check if docker CLI is available."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def collect(self) -> dict[str, Any]:
        result = {}
        try:
            proc = subprocess.run(
                [
                    "docker", "ps", "--format",
                    '{"id":"{{.ID}}","name":"{{.Names}}","image":"{{.Image}}",'
                    '"status":"{{.Status}}","ports":"{{.Ports}}"}',
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                return result

            for line in proc.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    container = json.loads(line)
                    name = container.get("name", container.get("id", "unknown"))
                    result[name] = {
                        "id": container.get("id"),
                        "image": container.get("image"),
                        "status": container.get("status"),
                        "ports": container.get("ports"),
                    }
                except json.JSONDecodeError:
                    continue

        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if old is None:
            return f"+ Container '{key}' started (image: {new.get('image', '?')})"
        if new is None:
            return f"- Container '{key}' stopped (was image: {old.get('image', '?')})"
        changes = []
        if old.get("status") != new.get("status"):
            changes.append(f"status: {old.get('status')} -> {new.get('status')}")
        if old.get("image") != new.get("image"):
            changes.append(f"image: {old.get('image')} -> {new.get('image')}")
        return f"  Container '{key}': {', '.join(changes)}"
