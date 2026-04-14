"""Config file checksum collector."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector

# Common config files to watch
_DEFAULT_WATCH_PATTERNS = [
    ".env",
    ".env.*",
    "*.json",
    "*.yaml",
    "*.yml",
    "*.toml",
    "*.ini",
    "*.cfg",
    "*.conf",
    "Makefile",
    "Dockerfile",
    "docker-compose*.yml",
    "docker-compose*.yaml",
    ".gitignore",
    "requirements*.txt",
    "package.json",
    "package-lock.json",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
]


def _sha256_file(path: Path) -> str | None:
    """Compute SHA-256 hash of a file."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]  # Short hash is enough
    except (OSError, PermissionError):
        return None


def _file_info(path: Path) -> dict[str, Any] | None:
    """Get file info: hash, size, mtime."""
    try:
        stat = path.stat()
        sha = _sha256_file(path)
        if sha is None:
            return None
        return {
            "sha256": sha,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
        }
    except (OSError, PermissionError):
        return None


class FileCollector(Collector):
    """Collects checksums of config files in the current directory tree."""

    name = "files"

    def __init__(self, root: str | None = None, max_depth: int = 3):
        self.root = Path(root) if root else Path.cwd()
        self.max_depth = max_depth

    def collect(self) -> dict[str, Any]:
        result = {}
        self._scan_dir(self.root, 0, result)
        return result

    def _scan_dir(self, directory: Path, depth: int, result: dict[str, Any]) -> None:
        if depth > self.max_depth:
            return
        try:
            entries = sorted(directory.iterdir())
        except (PermissionError, OSError):
            return

        for entry in entries:
            if entry.is_dir():
                # Skip hidden dirs, node_modules, etc.
                if entry.name.startswith(".") or entry.name in (
                    "node_modules", "__pycache__", ".git", "venv", ".venv",
                    "target", "dist", "build",
                ):
                    continue
                self._scan_dir(entry, depth + 1, result)
            elif entry.is_file():
                if self._should_watch(entry):
                    info = _file_info(entry)
                    if info:
                        rel = str(entry.relative_to(self.root))
                        result[rel] = info

    def _should_watch(self, path: Path) -> bool:
        name = path.name
        for pattern in _DEFAULT_WATCH_PATTERNS:
            if "*" in pattern:
                # Simple glob matching
                prefix, suffix = pattern.split("*", 1)
                if name.startswith(prefix) and name.endswith(suffix):
                    return True
            elif name == pattern or name.startswith(pattern):
                return True
        return False

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if old is None:
            return f"+ {key} (new file, {new.get('size', '?')} bytes)"
        if new is None:
            return f"- {key} (deleted)"
        old_hash = old.get("sha256", "?")
        new_hash = new.get("sha256", "?")
        if old_hash != new_hash:
            return f"  {key}: content changed ({old.get('size')}->{new.get('size')} bytes)"
        return f"  {key}: metadata changed"
