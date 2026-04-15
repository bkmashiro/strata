"""Snapshot creation logic."""

from __future__ import annotations

import platform
from typing import Any

from strata.collectors import ALL_COLLECTORS, Collector
from strata.storage import SnapshotStore


def create_snapshot(
    store: SnapshotStore,
    label: str | None = None,
    collectors: list[str] | None = None,
    file_root: str | None = None,
    include_git: bool = True,
    git_hook: bool = False,
) -> dict[str, Any]:
    """Create a new environment snapshot.

    Args:
        store: The snapshot store to save to.
        label: Optional human-readable label.
        collectors: Optional list of collector names to use.
            If None, uses all available collectors.
        file_root: Optional root directory for the file collector.
        include_git: Whether to detect and attach git context (default True).
        git_hook: If True, running from a git hook. Auto-labels as git:<short_hash>.

    Returns:
        The saved snapshot dict including its ID.
    """
    data: dict[str, dict[str, Any]] = {}
    collector_names_used: list[str] = []
    errors: dict[str, str] = {}

    for cls in ALL_COLLECTORS:
        # Filter by name if specified
        if collectors and cls.name not in collectors:
            continue

        # Check availability
        if not cls.is_available():
            continue

        try:
            if cls.name == "files" and file_root:
                instance = cls(root=file_root)
            else:
                instance = cls()
            collected = instance.collect()
            data[cls.name] = collected
            collector_names_used.append(cls.name)
        except Exception as e:
            errors[cls.name] = str(e)

    metadata: dict[str, Any] = {
        "collectors": collector_names_used,
        "errors": errors,
    }

    # Capture git context if requested
    if include_git:
        try:
            from strata.git_integration import get_git_context
            git_ctx = get_git_context(file_root or ".")
            if git_ctx:
                metadata["git_commit"] = git_ctx["commit"]
                metadata["git_commit_short"] = git_ctx["commit_short"]
                metadata["git_branch"] = git_ctx["branch"]
                metadata["git_message"] = git_ctx["message"]
                metadata["git_repo"] = git_ctx["repo_root"]
                metadata["git_repo_name"] = git_ctx["repo_name"]
                metadata["git_is_dirty"] = git_ctx["is_dirty"]

                # Auto-label from git hook
                if git_hook and not label:
                    label = f"git:{git_ctx['commit_short']}"
        except Exception:
            pass  # Silently skip git context on any error

    snapshot_id = store.save_snapshot(
        data=data,
        label=label,
        hostname=platform.node(),
        metadata=metadata,
    )

    snapshot = store.get_snapshot(snapshot_id)
    return snapshot
