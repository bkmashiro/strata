"""Git integration for Strata -- links snapshots to git commits."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


HOOK_MARKER = "# strata environment snapshot hook"
HOOK_CONTENT = f"""#!/bin/sh
{HOOK_MARKER}
strata snap --git-hook --quiet 2>/dev/null || true
"""


def _run_git(args: list[str], cwd: str | None = None) -> str | None:
    """Run a git command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def get_git_context(path: str = ".") -> dict[str, Any] | None:
    """If path is inside a git repo, return git context dict.

    Returns:
        Dict with commit, commit_short, branch, message, author,
        timestamp, repo_root, repo_name, is_dirty.
        None if not in a git repo or git not available.
    """
    repo_root = _run_git(["rev-parse", "--show-toplevel"], cwd=path)
    if repo_root is None:
        return None

    commit = _run_git(["rev-parse", "HEAD"], cwd=path)
    if commit is None:
        return None

    commit_short = _run_git(["rev-parse", "--short", "HEAD"], cwd=path) or commit[:7]
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=path) or ""
    message = _run_git(["log", "-1", "--format=%s"], cwd=path) or ""
    author = _run_git(["log", "-1", "--format=%an <%ae>"], cwd=path) or ""
    timestamp = _run_git(["log", "-1", "--format=%aI"], cwd=path) or ""

    # Check for uncommitted changes
    dirty_check = _run_git(["status", "--porcelain"], cwd=path)
    is_dirty = bool(dirty_check)

    repo_name = Path(repo_root).name

    return {
        "commit": commit,
        "commit_short": commit_short,
        "branch": branch,
        "message": message,
        "author": author,
        "timestamp": timestamp,
        "repo_root": repo_root,
        "repo_name": repo_name,
        "is_dirty": is_dirty,
    }


def _get_hooks_dir(repo_path: str = ".") -> Path | None:
    """Get the hooks directory for a git repo."""
    repo_root = _run_git(["rev-parse", "--show-toplevel"], cwd=repo_path)
    if repo_root is None:
        return None
    hooks_dir = Path(repo_root) / ".git" / "hooks"
    if not hooks_dir.is_dir():
        hooks_dir.mkdir(parents=True, exist_ok=True)
    return hooks_dir


def install_hook(repo_path: str = ".") -> str:
    """Install a post-commit hook in the git repo at repo_path.

    Returns the hook file path.
    Raises FileNotFoundError if not in a git repo.
    Raises FileExistsError if strata hook already installed.
    If a hook already exists (not from strata), appends to it.
    """
    hooks_dir = _get_hooks_dir(repo_path)
    if hooks_dir is None:
        raise FileNotFoundError("Not inside a git repository")

    hook_path = hooks_dir / "post-commit"

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            raise FileExistsError(
                f"Strata hook already installed at {hook_path}"
            )
        # Append to existing hook
        append_content = f"\n{HOOK_MARKER}\nstrata snap --git-hook --quiet 2>/dev/null || true\n"
        with open(hook_path, "a") as f:
            f.write(append_content)
    else:
        hook_path.write_text(HOOK_CONTENT)

    # Make executable
    hook_path.chmod(0o755)
    return str(hook_path)


def uninstall_hook(repo_path: str = ".") -> bool:
    """Remove strata's hook. Returns True if removed, False if not found."""
    hooks_dir = _get_hooks_dir(repo_path)
    if hooks_dir is None:
        return False

    hook_path = hooks_dir / "post-commit"
    if not hook_path.exists():
        return False

    content = hook_path.read_text()
    if HOOK_MARKER not in content:
        return False

    lines = content.split("\n")
    new_lines = []
    skip_next = False
    for line in lines:
        if HOOK_MARKER in line:
            skip_next = True
            continue
        if skip_next:
            # Skip the strata command line that follows the marker
            if "strata snap" in line:
                skip_next = False
                continue
            skip_next = False
        new_lines.append(line)

    new_content = "\n".join(new_lines).strip()

    if not new_content or new_content == "#!/bin/sh":
        # Nothing left, remove the file
        hook_path.unlink()
    else:
        hook_path.write_text(new_content + "\n")

    return True


def is_hook_installed(repo_path: str = ".") -> bool:
    """Check if strata hook is installed in this repo."""
    hooks_dir = _get_hooks_dir(repo_path)
    if hooks_dir is None:
        return False

    hook_path = hooks_dir / "post-commit"
    if not hook_path.exists():
        return False

    return HOOK_MARKER in hook_path.read_text()
