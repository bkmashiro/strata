"""SSH key fingerprint collector (never captures private keys)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector


def _get_pub_key_info(pub_path: Path) -> dict[str, str] | None:
    """Get fingerprint and type for a public key file."""
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-lf", str(pub_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return None
        # Output format: "256 SHA256:xxx comment (TYPE)"
        output = proc.stdout.strip()
        parts = output.split()
        if len(parts) >= 4:
            bits = parts[0]
            fingerprint = parts[1]
            key_type = parts[-1].strip("()")
            comment = " ".join(parts[2:-1])
            return {
                "filename": pub_path.name,
                "fingerprint": fingerprint,
                "bits": bits,
                "key_type": key_type,
                "comment": comment,
            }
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _count_lines(path: Path) -> int:
    """Count non-empty, non-comment lines in a file."""
    try:
        count = 0
        for line in path.read_text(errors="replace").split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                count += 1
        return count
    except (OSError, PermissionError):
        return 0


def _get_loaded_keys() -> list[dict[str, str]]:
    """Get fingerprints of keys loaded in ssh-agent."""
    try:
        proc = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            return []
        keys = []
        for line in proc.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 3:
                keys.append({
                    "bits": parts[0],
                    "fingerprint": parts[1],
                    "comment": " ".join(parts[2:]).rstrip(")").rstrip(" ").split(" (")[0] if len(parts) > 2 else "",
                    "key_type": parts[-1].strip("()") if parts[-1].startswith("(") else "",
                })
        return keys
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


class SSHKeysCollector(Collector):
    """Collects SSH key fingerprints and metadata (never private keys)."""

    name = "ssh_keys"

    def collect(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        ssh_dir = Path.home() / ".ssh"

        if not ssh_dir.is_dir():
            return result

        # Collect public key fingerprints
        pub_keys = {}
        try:
            for entry in sorted(ssh_dir.iterdir()):
                if entry.is_file() and entry.suffix == ".pub":
                    info = _get_pub_key_info(entry)
                    if info:
                        pub_keys[entry.name] = info
        except (PermissionError, OSError):
            pass

        if pub_keys:
            result["pub_keys"] = pub_keys

        # Count known_hosts entries
        known_hosts = ssh_dir / "known_hosts"
        if known_hosts.is_file():
            result["known_hosts_count"] = _count_lines(known_hosts)

        # Count authorized_keys entries
        authorized_keys = ssh_dir / "authorized_keys"
        if authorized_keys.is_file():
            result["authorized_keys_count"] = _count_lines(authorized_keys)

        # Loaded keys in ssh-agent
        loaded = _get_loaded_keys()
        if loaded:
            result["loaded_agent_keys"] = loaded

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if key == "known_hosts_count":
            return f"  known_hosts: {old} -> {new} entries"
        if key == "authorized_keys_count":
            return f"  authorized_keys: {old} -> {new} entries"
        if key == "pub_keys":
            if old is None:
                return f"+ SSH public keys found ({len(new)} keys)"
            if new is None:
                return f"- SSH public keys no longer found"
            old_set = set(old.keys()) if isinstance(old, dict) else set()
            new_set = set(new.keys()) if isinstance(new, dict) else set()
            added = new_set - old_set
            removed = old_set - new_set
            parts = []
            if added:
                parts.append(f"+{len(added)}")
            if removed:
                parts.append(f"-{len(removed)}")
            return f"  SSH public keys: {' '.join(parts)}" if parts else "  SSH public keys: changed"
        if old is None:
            return f"+ {key}"
        if new is None:
            return f"- {key}"
        return f"  {key}: changed"
