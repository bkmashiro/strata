"""CLI interface for Strata."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

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
    """Resolve a snapshot reference: ID number, label, 'latest', or 'git:<hash>'."""
    if ref.lower() == "latest":
        snaps = store.get_latest(1)
        if snaps:
            return store.get_snapshot(snaps[0]["id"])
        return None

    # git:<hash> reference
    if ref.startswith("git:"):
        commit_hash = ref[4:]
        return store.find_by_git_commit(commit_hash)

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
@click.option(
    "--git-hook", is_flag=True, default=False,
    help="Running from git hook: auto-label with commit hash",
)
@click.option(
    "--no-git", is_flag=True, default=False,
    help="Skip git context detection",
)
@click.option(
    "--quiet", "-q", is_flag=True, default=False,
    help="Minimal output",
)
@click.pass_context
def snap(
    ctx: click.Context,
    label: str | None,
    collectors: tuple[str, ...],
    root: str | None,
    git_hook: bool,
    no_git: bool,
    quiet: bool,
) -> None:
    """Take a snapshot of the current environment state."""
    store = _get_store(ctx)
    try:
        if not quiet:
            with console.status("[bold blue]Collecting environment state...[/bold blue]"):
                snapshot = create_snapshot(
                    store=store,
                    label=label,
                    collectors=list(collectors) if collectors else None,
                    file_root=root,
                    include_git=not no_git,
                    git_hook=git_hook,
                )
        else:
            snapshot = create_snapshot(
                store=store,
                label=label,
                collectors=list(collectors) if collectors else None,
                file_root=root,
                include_git=not no_git,
                git_hook=git_hook,
            )

        if not quiet:
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

    REF can be a snapshot ID, label, 'latest', or 'git:<hash>'.
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

    OLD_REF and NEW_REF can be snapshot IDs, labels, 'latest', or 'git:<hash>'.
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

        # Show git hook status
        from strata.git_integration import is_hook_installed, get_git_context
        git_ctx = get_git_context()
        if git_ctx:
            console.print(f"\n[bold]Git:[/bold] {git_ctx['repo_name']} ({git_ctx['branch']})")
            console.print(f"  Commit: {git_ctx['commit_short']} {git_ctx['message']}")
            hook_status = "[green]installed[/green]" if is_hook_installed() else "[dim]not installed[/dim]"
            console.print(f"  Hook: {hook_status}")

        console.print("\n[bold]Available collectors:[/bold]")
        from strata.collectors import ALL_COLLECTORS
        for cls in ALL_COLLECTORS:
            available = cls.is_available()
            symbol = "[green]OK[/green]" if available else "[red]N/A[/red]"
            console.print(f"  {symbol}  {cls.name}")

    finally:
        store.close()


# --- Hooks command group ---

@main.group()
def hooks() -> None:
    """Manage git post-commit hooks."""
    pass


@hooks.command("install")
@click.option("--repo", default=".", help="Path to git repository")
def hooks_install(repo: str) -> None:
    """Install strata post-commit hook in a git repo."""
    from strata.git_integration import install_hook
    try:
        path = install_hook(repo)
        console.print(f"[green]Hook installed at {path}[/green]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except FileExistsError as e:
        console.print(f"[yellow]{e}[/yellow]")


@hooks.command("uninstall")
@click.option("--repo", default=".", help="Path to git repository")
def hooks_uninstall(repo: str) -> None:
    """Remove strata post-commit hook from a git repo."""
    from strata.git_integration import uninstall_hook
    if uninstall_hook(repo):
        console.print("[green]Hook removed[/green]")
    else:
        console.print("[yellow]No strata hook found[/yellow]")


@hooks.command("status")
@click.option("--repo", default=".", help="Path to git repository")
def hooks_status(repo: str) -> None:
    """Check if strata hook is installed."""
    from strata.git_integration import is_hook_installed
    if is_hook_installed(repo):
        console.print("[green]Strata hook is installed[/green]")
    else:
        console.print("[dim]Strata hook is not installed[/dim]")


# --- Git log command ---

@main.command("gitlog")
@click.option("-n", "--limit", default=30, help="Max commits to show")
@click.option("--repo", default=".", help="Path to git repository")
@click.option("--db", "db_path", type=click.Path(), default=None, help="Path to database file")
@click.pass_context
def gitlog(ctx: click.Context, limit: int, repo: str, db_path: str | None) -> None:
    """Show commits with linked strata snapshots.

    Displays git log merged with strata snapshot data, showing which
    commits have associated environment snapshots.
    """
    from strata.git_integration import _run_git

    # Get git log
    log_output = _run_git(
        ["log", f"-{limit}", "--format=%H|%h|%s|%an|%aI|%D"],
        cwd=repo,
    )
    if not log_output:
        console.print("[red]Not in a git repository or no commits found[/red]")
        sys.exit(1)

    store = _get_store(ctx)
    try:
        # Build a map of commit hash -> snapshot
        git_snaps = store.get_git_snapshots()
        commit_map: dict[str, dict] = {}
        for s in git_snaps:
            meta = s.get("metadata", {})
            commit = meta.get("git_commit", "")
            if commit:
                commit_map[commit] = s

        # Parse and display
        table = Table(show_header=True, border_style="blue", title="Git Log + Snapshots")
        table.add_column("", width=1)
        table.add_column("Hash", style="yellow")
        table.add_column("Message")
        table.add_column("Branch", style="cyan")
        table.add_column("Date", style="dim")
        table.add_column("Snapshot", style="green")

        for line in log_output.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 5)
            if len(parts) < 5:
                continue
            full_hash, short_hash, message, author, date_str = parts[0], parts[1], parts[2], parts[3], parts[4]
            refs = parts[5] if len(parts) > 5 else ""

            # Extract branch from refs
            branch = ""
            if refs:
                for ref_part in refs.split(","):
                    ref_part = ref_part.strip()
                    if ref_part.startswith("HEAD -> "):
                        branch = ref_part[8:]
                        break
                    elif "/" not in ref_part and ref_part != "HEAD":
                        branch = ref_part

            # Format date
            try:
                dt = datetime.fromisoformat(date_str)
                date_display = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                date_display = date_str[:16]

            # Check for snapshot
            snap = commit_map.get(full_hash)
            if snap:
                marker = "[green]\u25cf[/green]"
                snap_label = f"[snap #{snap['id']}]"
            else:
                marker = " "
                snap_label = ""

            # Truncate message
            if len(message) > 40:
                message = message[:37] + "..."

            table.add_row(marker, short_hash, message, branch, date_display, snap_label)

        console.print(table)
    finally:
        store.close()


# --- Bisect command ---

@main.command()
@click.argument("collector", type=click.Choice(COLLECTOR_NAMES))
@click.argument("key")
@click.option("--db", "db_path", type=click.Path(), default=None, help="Path to database file")
@click.pass_context
def bisect(ctx: click.Context, collector: str, key: str, db_path: str | None) -> None:
    """Show value history of a key across git-linked snapshots.

    Traces how a specific collector key changed across commits.
    Example: strata bisect packages python3
    """
    store = _get_store(ctx)
    try:
        git_snaps = store.get_git_snapshots()
        if not git_snaps:
            console.print("[yellow]No git-linked snapshots found[/yellow]")
            return

        table = Table(
            title=f"Bisect: {collector}/{key}",
            show_header=True,
            border_style="blue",
        )
        table.add_column("Commit", style="yellow")
        table.add_column("Message")
        table.add_column("Branch", style="cyan")
        table.add_column("Value")
        table.add_column("Changed", style="bold")

        prev_value = None
        found_any = False

        # Reverse to show oldest first
        for snap_meta in reversed(git_snaps):
            snap_id = snap_meta["id"]
            meta = snap_meta.get("metadata", {})
            commit_short = meta.get("git_commit_short", "?")
            message = meta.get("git_message", "")
            branch = meta.get("git_branch", "")

            # Load full snapshot to get data
            full_snap = store.get_snapshot(snap_id)
            if not full_snap:
                continue

            coll_data = full_snap.get("data", {}).get(collector, {})
            value = coll_data.get(key)

            if value is None:
                continue

            found_any = True
            value_str = str(value)
            if len(value_str) > 50:
                value_str = value_str[:47] + "..."

            if len(message) > 30:
                message = message[:27] + "..."

            changed = ""
            if prev_value is not None and value != prev_value:
                changed = "[red]\u2190 changed[/red]"
            elif prev_value is None:
                changed = "[dim]initial[/dim]"

            prev_value = value

            table.add_row(commit_short, message, branch, value_str, changed)

        if found_any:
            console.print(table)
        else:
            console.print(f"[yellow]Key '{key}' not found in '{collector}' across git-linked snapshots[/yellow]")
    finally:
        store.close()


if __name__ == "__main__":
    main()
