"""CLI interface for Strata."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from strata import __version__
from strata.storage import SnapshotStore
from strata.snapshot import create_snapshot
from strata.diff import diff_snapshots, format_diff, summarize_diff
from strata.display import (
    display_snapshot_summary,
    display_snapshot_list,
    display_diff,
    display_search_results,
    display_collector_detail,
)

console = Console()

COLLECTOR_NAMES = [
    "envvars", "processes", "network", "files",
    "disk", "system", "docker", "packages",
]


def _resolve_snapshot_ref(store: SnapshotStore, ref: str) -> dict | None:
    """Resolve a snapshot reference: ID number, label, or 'latest'."""
    if ref.lower() == "latest":
        snaps = store.get_latest(1)
        if snaps:
            return store.get_snapshot(snaps[0]["id"])
        return None

    # Try as integer ID
    try:
        snap_id = int(ref)
        return store.get_snapshot(snap_id)
    except ValueError:
        pass

    # Try as label
    return store.find_by_label(ref)


@click.group()
@click.version_option(__version__, prog_name="strata")
@click.option("--db", type=click.Path(), default=None, help="Path to database file")
@click.pass_context
def main(ctx: click.Context, db: Optional[str]) -> None:
    """Strata - Environment Archaeology Tool.

    Snapshot, diff, and debug your development environment state.
    """
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db


def _get_store(ctx: click.Context) -> SnapshotStore:
    return SnapshotStore(ctx.obj.get("db_path"))


@main.command()
@click.option("-l", "--label", default=None, help="Label for this snapshot")
@click.option(
    "-c", "--collector", "collectors", multiple=True,
    type=click.Choice(COLLECTOR_NAMES),
    help="Specific collectors to run (default: all)",
)
@click.option(
    "--root", default=None,
    help="Root directory for file collector (default: cwd)",
)
@click.pass_context
def snap(ctx: click.Context, label: str | None, collectors: tuple[str, ...], root: str | None) -> None:
    """Take a snapshot of the current environment state."""
    store = _get_store(ctx)
    try:
        with console.status("[bold blue]Collecting environment state...[/bold blue]"):
            snapshot = create_snapshot(
                store=store,
                label=label,
                collectors=list(collectors) if collectors else None,
                file_root=root,
            )
        console.print(f"[green]Snapshot #{snapshot['id']} saved[/green]")
        display_snapshot_summary(console, snapshot)
    finally:
        store.close()


@main.command()
@click.option("-n", "--limit", default=20, help="Number of snapshots to show")
@click.pass_context
def ls(ctx: click.Context, limit: int) -> None:
    """List saved snapshots."""
    store = _get_store(ctx)
    try:
        snapshots = store.list_snapshots(limit)
        display_snapshot_list(console, snapshots)
    finally:
        store.close()


@main.command()
@click.argument("ref")
@click.option(
    "-c", "--collector", default=None,
    type=click.Choice(COLLECTOR_NAMES),
    help="Show detail for a specific collector",
)
@click.pass_context
def show(ctx: click.Context, ref: str, collector: str | None) -> None:
    """Show details of a snapshot.

    REF can be a snapshot ID, label, or 'latest'.
    """
    store = _get_store(ctx)
    try:
        snapshot = _resolve_snapshot_ref(store, ref)
        if not snapshot:
            console.print(f"[red]Snapshot '{ref}' not found[/red]")
            sys.exit(1)

        if collector:
            display_collector_detail(console, snapshot, collector)
        else:
            display_snapshot_summary(console, snapshot)
    finally:
        store.close()


@main.command()
@click.argument("old_ref")
@click.argument("new_ref", default="latest")
@click.option(
    "-c", "--collector", "collectors", multiple=True,
    type=click.Choice(COLLECTOR_NAMES),
    help="Limit diff to specific collectors",
)
@click.pass_context
def diff(ctx: click.Context, old_ref: str, new_ref: str, collectors: tuple[str, ...]) -> None:
    """Diff two snapshots.

    OLD_REF and NEW_REF can be snapshot IDs, labels, or 'latest'.
    If NEW_REF is omitted, it defaults to 'latest'.
    """
    store = _get_store(ctx)
    try:
        old_snap = _resolve_snapshot_ref(store, old_ref)
        if not old_snap:
            console.print(f"[red]Snapshot '{old_ref}' not found[/red]")
            sys.exit(1)

        new_snap = _resolve_snapshot_ref(store, new_ref)
        if not new_snap:
            console.print(f"[red]Snapshot '{new_ref}' not found[/red]")
            sys.exit(1)

        diff_result = diff_snapshots(
            old_snap, new_snap,
            collectors=list(collectors) if collectors else None,
        )
        entries = format_diff(diff_result)
        summary = summarize_diff(diff_result)
        display_diff(console, entries, summary, old_snap, new_snap)
    finally:
        store.close()


@main.command()
@click.argument("ref")
@click.pass_context
def rm(ctx: click.Context, ref: str) -> None:
    """Delete a snapshot.

    REF can be a snapshot ID or label.
    """
    store = _get_store(ctx)
    try:
        snapshot = _resolve_snapshot_ref(store, ref)
        if not snapshot:
            console.print(f"[red]Snapshot '{ref}' not found[/red]")
            sys.exit(1)

        snap_id = snapshot["id"]
        label = snapshot.get("label") or f"#{snap_id}"
        if store.delete_snapshot(snap_id):
            console.print(f"[green]Deleted snapshot {label} (#{snap_id})[/green]")
        else:
            console.print(f"[red]Failed to delete snapshot {label}[/red]")
    finally:
        store.close()


@main.command()
@click.argument("collector", type=click.Choice(COLLECTOR_NAMES))
@click.argument("query")
@click.pass_context
def search(ctx: click.Context, collector: str, query: str) -> None:
    """Search for a key across snapshots.

    Searches within a specific collector's data for keys matching QUERY.
    Example: strata search envvars PATH
    """
    store = _get_store(ctx)
    try:
        results = store.search(collector, query)
        display_search_results(console, results, query)
    finally:
        store.close()


@main.command()
@click.option("-l", "--label", default="baseline", help="Label for the baseline snapshot")
@click.option(
    "--root", default=None,
    help="Root directory for file collector (default: cwd)",
)
@click.pass_context
def doctor(ctx: click.Context, label: str, root: str | None) -> None:
    """Compare current state against a labeled baseline.

    Takes a fresh snapshot and diffs it against the snapshot with the given label.
    If no baseline exists, the current snapshot becomes the baseline.
    """
    store = _get_store(ctx)
    try:
        baseline = store.find_by_label(label)

        if not baseline:
            console.print(f"[yellow]No baseline '{label}' found. Creating one now...[/yellow]")
            with console.status("[bold blue]Creating baseline...[/bold blue]"):
                snapshot = create_snapshot(store=store, label=label, file_root=root)
            console.print(f"[green]Baseline #{snapshot['id']} created with label '{label}'[/green]")
            console.print("[dim]Run 'strata doctor' again later to compare against this baseline.[/dim]")
            display_snapshot_summary(console, snapshot)
            return

        # Take a fresh snapshot
        with console.status("[bold blue]Taking fresh snapshot...[/bold blue]"):
            current = create_snapshot(store=store, label=None, file_root=root)

        console.print(f"[bold]Comparing against baseline '{label}' (#{baseline['id']})[/bold]\n")

        diff_result = diff_snapshots(baseline, current)
        entries = format_diff(diff_result)
        summary = summarize_diff(diff_result)
        display_diff(console, entries, summary, baseline, current)

    finally:
        store.close()


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show quick status: latest snapshot summary and available collectors."""
    store = _get_store(ctx)
    try:
        count = store.count()
        console.print(f"[bold]Strata v{__version__}[/bold]")
        console.print(f"Database: {store.db_path}")
        console.print(f"Snapshots: {count}")

        if count > 0:
            latest = store.get_latest(1)
            if latest:
                snap = latest[0]
                from strata.display import _format_timestamp, _format_age
                console.print(
                    f"Latest: #{snap['id']} "
                    f"({snap.get('label') or 'unlabeled'}) "
                    f"at {_format_timestamp(snap['timestamp'])} "
                    f"({_format_age(snap['timestamp'])})"
                )

        console.print("\n[bold]Available collectors:[/bold]")
        from strata.collectors import ALL_COLLECTORS
        for cls in ALL_COLLECTORS:
            available = cls.is_available()
            symbol = "[green]OK[/green]" if available else "[red]N/A[/red]"
            console.print(f"  {symbol}  {cls.name}")

    finally:
        store.close()


if __name__ == "__main__":
    main()
