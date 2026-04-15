"""Git repository state collector."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector

_MAX_REPOS = 50
_MAX_DEPTH = 3

# Common directories to scan for git repos
_SCAN_DIRS = [
    Path.home(),
    Path.home() / "projects",
    Path.home() / "code",
    Path.home() / "workspace",
    Path.home() / "dev",
]


def _git_cmd(repo_path: str, args: list[str], timeout: int = 5) -> str | None:
    """Run a git command in a repo and return stdout."""
    try:
        proc = subprocess.run(
            ["git", "-C", repo_path] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _get_repo_info(repo_path: str) -> dict[str, Any] | None:
    """Get state information for a git repository."""
    try:
        commit_hash = _git_cmd(repo_path, ["rev-parse", "HEAD"])
        if not commit_hash:
            return None

        branch = _git_cmd(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"

        commit_message = _git_cmd(repo_path, ["log", "-1", "--format=%s"])

        status_output = _git_cmd(repo_path, ["status", "--short"])
        is_dirty = bool(status_output)

        remote_url = _git_cmd(repo_path, ["remote", "get-url", "origin"])

        return {
            "path": repo_path,
            "branch": branch,
            "commit_hash": commit_hash[:12],
            "commit_message": (commit_message or "")[:120],
            "is_dirty": is_dirty,
            "remote_url": remote_url or "",
        }
    except Exception:
        return None


def _find_git_repos(
    scan_dirs: list[Path],
    max_depth: int = _MAX_DEPTH,
    max_repos: int = _MAX_REPOS,
) -> list[str]:
    """Find git repositories by scanning directories."""
    repos: list[str] = []
    visited: set[str] = set()

    def _scan(directory: Path, depth: int) -> None:
        if depth > max_depth or len(repos) >= max_repos:
            return

        try:
            resolved = str(directory.resolve())
        except (OSError, ValueError):
            return

        if resolved in visited:
            return
        visited.add(resolved)

        try:
            if not directory.is_dir():
                return
        except (OSError, PermissionError):
            return

        git_dir = directory / ".git"
        try:
            if git_dir.exists():
                repos.append(str(directory))
                return  # Don't scan subdirectories of a git repo
        except (OSError, PermissionError):
            pass

        try:
            entries = sorted(directory.iterdir())
        except (PermissionError, OSError):
            return

        for entry in entries:
            if len(repos) >= max_repos:
                return
            try:
                if not entry.is_dir():
                    continue
                name = entry.name
                # Skip hidden dirs (except for the target .git check above), large dirs
                if name.startswith(".") or name in (
                    "node_modules", "__pycache__", "venv", ".venv",
                    "target", "dist", "build", "vendor", "Library",
                    "Applications", ".cache", ".local",
                ):
                    continue
                _scan(entry, depth + 1)
            except (PermissionError, OSError):
                continue

    for scan_dir in scan_dirs:
        if len(repos) >= max_repos:
            break
        _scan(scan_dir, 0)

    return repos[:max_repos]


class GitReposCollector(Collector):
    """Collects git repository states from common directories."""

    name = "gitrepos"

    def __init__(self, extra_roots: list[str] | None = None):
        self.extra_roots = extra_roots or []

    def collect(self) -> dict[str, Any]:
        scan_dirs = list(_SCAN_DIRS)

        # Add cwd
        try:
            cwd = Path.cwd()
            if cwd not in scan_dirs:
                scan_dirs.append(cwd)
        except OSError:
            pass

        # Add extra roots
        for root in self.extra_roots:
            p = Path(root)
            if p not in scan_dirs:
                scan_dirs.append(p)

        # Filter to directories that actually exist
        scan_dirs = [d for d in scan_dirs if d.is_dir()]

        repo_paths = _find_git_repos(scan_dirs)

        result = {}
        for repo_path in repo_paths:
            info = _get_repo_info(repo_path)
            if info:
                result[repo_path] = info

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        repo_name = Path(key).name if "/" in key else key
        if old is None:
            branch = new.get("branch", "?")
            return f"+ {repo_name}: new repo found ({branch})"
        if new is None:
            return f"- {repo_name}: repo no longer found"
        changes = []
        if old.get("branch") != new.get("branch"):
            changes.append(f"branch: {old.get('branch')} -> {new.get('branch')}")
        if old.get("commit_hash") != new.get("commit_hash"):
            changes.append(f"commit: {old.get('commit_hash', '?')[:8]} -> {new.get('commit_hash', '?')[:8]}")
        if old.get("is_dirty") != new.get("is_dirty"):
            state = "dirty" if new.get("is_dirty") else "clean"
            changes.append(f"now {state}")
        return f"  {repo_name}: {', '.join(changes)}" if changes else f"  {repo_name}: metadata changed"
