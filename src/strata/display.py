"""Terminal display formatting using Rich."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Seed-derived color palette (from seed numbers mod 256 mapped to rich colors)
# Seeds: 1368 1491 7612 8558 922 5711 9321 7761 6006 6187 8309 9914 8597 6943 3967 3644
_COLLECTOR_COLORS = {
    "envvars": "bright_green",
    "processes": "bright_cyan",
    "network": "bright_magenta",
    "files": "bright_yellow",
    "disk": "bright_blue",
    "system": "bright_white",
    "docker": "bright_red",
    "packages": "cyan",
}

_CHANGE_COLORS = {
    "added": "green",
    "removed": "red",
    "changed": "yellow",
}

_CHANGE_SYMBOLS = {
    "added": "+",
    "removed": "-",
    "changed": "~",
}


def _format_timestamp(ts: float) -> str:
    """Format a Unix timestamp for display."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_age(ts: float) -> str:
    """Format time elapsed since a timestamp."""
    elapsed = time.time() - ts
    if elapsed < 60:
        return f"{elapsed:.0f}s ago"
    elif elapsed < 3600:
        return f"{elapsed / 60:.0f}m ago"
    elif elapsed < 86400:
        return f"{elapsed / 3600:.1f}h ago"
    else:
        return f"{elapsed / 86400:.1f}d ago"


def display_snapshot_summary(console: Console, snapshot: dict[str, Any]) -> None:
    """Display a summary of a snapshot."""
    snap_id = snapshot.get("id", "?")
    label = snapshot.get("label") or "(unlabeled)"
    ts = snapshot.get("timestamp", 0)
    hostname = snapshot.get("hostname", "unknown")
    metadata = snapshot.get("metadata", {})
    data = snapshot.get("data", {})

    table = Table(title=f"Snapshot #{snap_id}: {label}", show_header=True, border_style="blue")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("ID", str(snap_id))
    table.add_row("Label", label)
    table.add_row("Time", _format_timestamp(ts))
    table.add_row("Host", hostname)
    table.add_row("Collectors", ", ".join(metadata.get("collectors", [])))

    if metadata.get("errors"):
        table.add_row("Errors", ", ".join(f"{k}: {v}" for k, v in metadata["errors"].items()))

    console.print(table)

    # Show counts per collector
    if data:
        counts_table = Table(show_header=True, border_style="dim")
        counts_table.add_column("Collector", style="bold")
        counts_table.add_column("Items", justify="right")

        for name, items in sorted(data.items()):
            color = _COLLECTOR_COLORS.get(name, "white")
            counts_table.add_row(
                Text(name, style=color),
                str(len(items)),
            )
        console.print(counts_table)


def display_snapshot_list(console: Console, snapshots: list[dict[str, Any]]) -> None:
    """Display a table of snapshots."""
    if not snapshots:
        console.print("[dim]No snapshots found.[/dim]")
        return

    table = Table(title="Snapshots", show_header=True, border_style="blue")
    table.add_column("ID", justify="right", style="bold")
    table.add_column("Label")
    table.add_column("Time")
    table.add_column("Age", justify="right")
    table.add_column("Host")
    table.add_column("Collectors", style="dim")

    for snap in snapshots:
        ts = snap.get("timestamp", 0)
        metadata = snap.get("metadata", {})
        collectors = metadata.get("collectors", [])
        table.add_row(
            str(snap.get("id", "?")),
            snap.get("label") or "-",
            _format_timestamp(ts),
            _format_age(ts),
            snap.get("hostname", "?"),
            ", ".join(collectors) if collectors else "-",
        )

    console.print(table)


def display_diff(
    console: Console,
    entries: list[dict[str, Any]],
    summary: dict[str, dict[str, int]],
    old_snap: dict[str, Any],
    new_snap: dict[str, Any],
) -> None:
    """Display a diff between two snapshots."""
    old_id = old_snap.get("id", "?")
    new_id = new_snap.get("id", "?")
    old_label = old_snap.get("label") or f"#{old_id}"
    new_label = new_snap.get("label") or f"#{new_id}"

    # Time delta
    old_ts = old_snap.get("timestamp", 0)
    new_ts = new_snap.get("timestamp", 0)
    delta_secs = new_ts - old_ts
    if delta_secs < 60:
        delta_str = f"{delta_secs:.0f}s"
    elif delta_secs < 3600:
        delta_str = f"{delta_secs / 60:.0f}m"
    elif delta_secs < 86400:
        delta_str = f"{delta_secs / 3600:.1f}h"
    else:
        delta_str = f"{delta_secs / 86400:.1f}d"

    if not entries:
        console.print(
            Panel(
                f"[green]No changes detected[/green] between {old_label} and {new_label} ({delta_str} apart)",
                title="Diff",
                border_style="green",
            )
        )
        return

    # Summary panel
    total_changes = sum(
        sum(counts.values()) for counts in summary.values()
    )
    summary_parts = []
    for coll_name, counts in sorted(summary.items()):
        color = _COLLECTOR_COLORS.get(coll_name, "white")
        parts = []
        if counts["added"]:
            parts.append(f"[green]+{counts['added']}[/green]")
        if counts["removed"]:
            parts.append(f"[red]-{counts['removed']}[/red]")
        if counts["changed"]:
            parts.append(f"[yellow]~{counts['changed']}[/yellow]")
        summary_parts.append(f"[{color}]{coll_name}[/{color}]: {' '.join(parts)}")

    console.print(
        Panel(
            f"[bold]{old_label}[/bold] -> [bold]{new_label}[/bold]  ({delta_str} apart)\n"
            + f"Total changes: {total_changes}\n"
            + " | ".join(summary_parts),
            title="Environment Diff",
            border_style="yellow",
        )
    )

    # Group entries by collector
    by_collector: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        coll = entry["collector"]
        by_collector.setdefault(coll, []).append(entry)

    for coll_name, coll_entries in sorted(by_collector.items()):
        color = _COLLECTOR_COLORS.get(coll_name, "white")
        console.print(f"\n[{color} bold]{coll_name}[/{color} bold]")

        for entry in coll_entries:
            change_type = entry["change_type"]
            symbol = _CHANGE_SYMBOLS[change_type]
            change_color = _CHANGE_COLORS[change_type]
            desc = entry["description"]
            console.print(f"  [{change_color}]{symbol}[/{change_color}] {desc}")


def display_search_results(
    console: Console, results: list[dict[str, Any]], query: str
) -> None:
    """Display search results."""
    if not results:
        console.print(f"[dim]No results found for '{query}'[/dim]")
        return

    table = Table(title=f"Search: '{query}'", show_header=True, border_style="blue")
    table.add_column("Snapshot", justify="right")
    table.add_column("Label")
    table.add_column("Time")
    table.add_column("Key", style="bold")
    table.add_column("Value")

    for r in results:
        value_str = str(r["value"])
        if len(value_str) > 60:
            value_str = value_str[:57] + "..."
        table.add_row(
            str(r["snapshot_id"]),
            r.get("label") or "-",
            _format_timestamp(r["timestamp"]),
            r["key"],
            value_str,
        )

    console.print(table)


def display_collector_detail(
    console: Console, snapshot: dict[str, Any], collector_name: str
) -> None:
    """Display detailed data for a single collector in a snapshot."""
    data = snapshot.get("data", {}).get(collector_name)
    if data is None:
        console.print(f"[red]Collector '{collector_name}' not found in snapshot[/red]")
        return

    color = _COLLECTOR_COLORS.get(collector_name, "white")
    table = Table(
        title=f"{collector_name} (Snapshot #{snapshot.get('id', '?')})",
        show_header=True,
        border_style=color,
    )
    table.add_column("Key", style="bold")
    table.add_column("Value")

    for key, value in sorted(data.items()):
        value_str = str(value)
        if len(value_str) > 80:
            value_str = value_str[:77] + "..."
        table.add_row(key, value_str)

    console.print(table)
