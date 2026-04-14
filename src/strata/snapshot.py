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
) -> dict[str, Any]:
    """Create a new environment snapshot.

    Args:
        store: The snapshot store to save to.
        label: Optional human-readable label.
        collectors: Optional list of collector names to use.
            If None, uses all available collectors.
        file_root: Optional root directory for the file collector.

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

    metadata = {
        "collectors": collector_names_used,
        "errors": errors,
    }

    snapshot_id = store.save_snapshot(
        data=data,
        label=label,
        hostname=platform.node(),
        metadata=metadata,
    )

    snapshot = store.get_snapshot(snapshot_id)
    return snapshot
