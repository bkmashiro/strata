"""Package/runtime version collector."""

from __future__ import annotations

import subprocess
from typing import Any

from strata.collectors.base import Collector

# Commands to check for runtime versions
_VERSION_COMMANDS = [
    ("node", ["node", "--version"]),
    ("npm", ["npm", "--version"]),
    ("python3", ["python3", "--version"]),
    ("pip", ["pip3", "--version"]),
    ("ruby", ["ruby", "--version"]),
    ("go", ["go", "version"]),
    ("rustc", ["rustc", "--version"]),
    ("cargo", ["cargo", "--version"]),
    ("java", ["java", "-version"]),  # outputs to stderr
    ("gcc", ["gcc", "--version"]),
    ("git", ["git", "--version"]),
    ("docker", ["docker", "--version"]),
    ("kubectl", ["kubectl", "version", "--client", "--short"]),
    ("terraform", ["terraform", "--version"]),
]


def _get_version(cmd: list[str]) -> str | None:
    """Run a version command and return the first line of output."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = proc.stdout.strip() or proc.stderr.strip()
        if output:
            return output.split("\n")[0].strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


class PackageCollector(Collector):
    """Collects installed package/runtime versions."""

    name = "packages"

    def collect(self) -> dict[str, Any]:
        result = {}
        for name, cmd in _VERSION_COMMANDS:
            version = _get_version(cmd)
            if version:
                result[name] = version
        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if old is None:
            return f"+ {key}: installed ({new})"
        if new is None:
            return f"- {key}: no longer found"
        return f"  {key}: {old} -> {new}"
