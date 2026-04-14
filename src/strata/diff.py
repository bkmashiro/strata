"""Snapshot diffing logic."""

from __future__ import annotations

from typing import Any

from strata.collectors import ALL_COLLECTORS


def _get_collector_class(name: str):
    """Look up a collector class by name."""
    for cls in ALL_COLLECTORS:
        if cls.name == name:
            return cls
    return None


def diff_dicts(
    old: dict[str, Any], new: dict[str, Any]
) -> dict[str, tuple[Any, Any]]:
    """Diff two flat dictionaries.

    Returns a dict mapping keys to (old_value, new_value) tuples.
    old_value is None if the key was added.
    new_value is None if the key was removed.
    Only changed keys are included.
    """
    changes = {}
    all_keys = set(old.keys()) | set(new.keys())

    for key in sorted(all_keys):
        old_val = old.get(key)
        new_val = new.get(key)

        if old_val is None and new_val is not None:
            changes[key] = (None, new_val)
        elif old_val is not None and new_val is None:
            changes[key] = (old_val, None)
        elif old_val != new_val:
            changes[key] = (old_val, new_val)

    return changes


def diff_snapshots(
    old_snap: dict[str, Any],
    new_snap: dict[str, Any],
    collectors: list[str] | None = None,
) -> dict[str, dict[str, tuple[Any, Any]]]:
    """Diff two full snapshots.

    Args:
        old_snap: The older snapshot (from store.get_snapshot()).
        new_snap: The newer snapshot.
        collectors: Optional filter for specific collectors.

    Returns:
        Dict mapping collector_name -> {key: (old_val, new_val)}.
        Only collectors with changes are included.
    """
    old_data = old_snap.get("data", {})
    new_data = new_snap.get("data", {})

    all_collectors = set(old_data.keys()) | set(new_data.keys())
    if collectors:
        all_collectors = all_collectors & set(collectors)

    result = {}
    for coll_name in sorted(all_collectors):
        old_coll = old_data.get(coll_name, {})
        new_coll = new_data.get(coll_name, {})
        changes = diff_dicts(old_coll, new_coll)
        if changes:
            result[coll_name] = changes

    return result


def format_diff(
    diff_result: dict[str, dict[str, tuple[Any, Any]]]
) -> list[dict[str, Any]]:
    """Format a diff result into displayable entries.

    Returns a list of entries, each with:
        - collector: str
        - key: str
        - old: Any
        - new: Any
        - change_type: "added" | "removed" | "changed"
        - description: str (human-readable)
    """
    entries = []

    for coll_name, changes in diff_result.items():
        collector_cls = _get_collector_class(coll_name)

        for key, (old_val, new_val) in changes.items():
            if old_val is None:
                change_type = "added"
            elif new_val is None:
                change_type = "removed"
            else:
                change_type = "changed"

            if collector_cls:
                description = collector_cls.diff_entry(key, old_val, new_val)
            else:
                description = f"{key}: {old_val!r} -> {new_val!r}"

            entries.append({
                "collector": coll_name,
                "key": key,
                "old": old_val,
                "new": new_val,
                "change_type": change_type,
                "description": description,
            })

    return entries


def summarize_diff(
    diff_result: dict[str, dict[str, tuple[Any, Any]]]
) -> dict[str, dict[str, int]]:
    """Summarize a diff: count of added/removed/changed per collector."""
    summary = {}
    for coll_name, changes in diff_result.items():
        counts = {"added": 0, "removed": 0, "changed": 0}
        for key, (old_val, new_val) in changes.items():
            if old_val is None:
                counts["added"] += 1
            elif new_val is None:
                counts["removed"] += 1
            else:
                counts["changed"] += 1
        summary[coll_name] = counts
    return summary
