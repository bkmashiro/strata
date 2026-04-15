"""Tests for git integration."""

import json
import os
import subprocess
import textwrap
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from strata.cli import main
from strata.git_integration import (
    HOOK_MARKER,
    get_git_context,
    install_hook,
    is_hook_installed,
    uninstall_hook,
    _run_git,
)
from strata.snapshot import create_snapshot
from strata.storage import SnapshotStore


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = SnapshotStore(db_path)
    yield s
    s.close()


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True)
    (repo / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, capture_output=True)
    return repo


# --- Tests for get_git_context ---

class TestGetGitContext:
    def test_returns_context_in_git_repo(self, git_repo):
        ctx = get_git_context(str(git_repo))
        assert ctx is not None
        assert "commit" in ctx
        assert len(ctx["commit"]) == 40  # full SHA
        assert "commit_short" in ctx
        assert len(ctx["commit_short"]) >= 7
        assert ctx["branch"] in ("main", "master")
        assert ctx["message"] == "initial commit"
        assert "Test" in ctx["author"]
        assert ctx["repo_name"] == "repo"
        assert ctx["is_dirty"] is False

    def test_returns_none_outside_git_repo(self, tmp_path):
        non_repo = tmp_path / "not-a-repo"
        non_repo.mkdir()
        ctx = get_git_context(str(non_repo))
        assert ctx is None

    def test_detects_dirty_state(self, git_repo):
        (git_repo / "dirty.txt").write_text("uncommitted")
        ctx = get_git_context(str(git_repo))
        assert ctx is not None
        assert ctx["is_dirty"] is True

    def test_detects_branch_name(self, git_repo):
        subprocess.run(["git", "checkout", "-b", "feature-xyz"], cwd=git_repo, capture_output=True)
        ctx = get_git_context(str(git_repo))
        assert ctx is not None
        assert ctx["branch"] == "feature-xyz"

    def test_includes_timestamp(self, git_repo):
        ctx = get_git_context(str(git_repo))
        assert ctx is not None
        assert ctx["timestamp"]  # non-empty ISO timestamp

    def test_repo_root_is_absolute(self, git_repo):
        ctx = get_git_context(str(git_repo))
        assert ctx is not None
        assert os.path.isabs(ctx["repo_root"])


# --- Tests for hook install/uninstall ---

class TestHookManagement:
    def test_install_creates_hook(self, git_repo):
        path = install_hook(str(git_repo))
        hook_file = Path(path)
        assert hook_file.exists()
        content = hook_file.read_text()
        assert HOOK_MARKER in content
        assert "strata snap --git-hook" in content

    def test_install_makes_executable(self, git_repo):
        path = install_hook(str(git_repo))
        assert os.access(path, os.X_OK)

    def test_install_raises_if_already_installed(self, git_repo):
        install_hook(str(git_repo))
        with pytest.raises(FileExistsError):
            install_hook(str(git_repo))

    def test_install_appends_to_existing_hook(self, git_repo):
        hooks_dir = git_repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        existing_hook = hooks_dir / "post-commit"
        existing_hook.write_text("#!/bin/sh\necho 'existing hook'\n")
        existing_hook.chmod(0o755)

        path = install_hook(str(git_repo))
        content = Path(path).read_text()
        assert "existing hook" in content
        assert HOOK_MARKER in content

    def test_install_raises_if_not_git_repo(self, tmp_path):
        non_repo = tmp_path / "not-repo"
        non_repo.mkdir()
        with pytest.raises(FileNotFoundError):
            install_hook(str(non_repo))

    def test_uninstall_removes_hook(self, git_repo):
        install_hook(str(git_repo))
        assert uninstall_hook(str(git_repo)) is True
        hook = git_repo / ".git" / "hooks" / "post-commit"
        assert not hook.exists()

    def test_uninstall_preserves_other_hooks(self, git_repo):
        hooks_dir = git_repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        existing_hook = hooks_dir / "post-commit"
        existing_hook.write_text("#!/bin/sh\necho 'keep me'\n")
        existing_hook.chmod(0o755)

        install_hook(str(git_repo))
        uninstall_hook(str(git_repo))

        content = existing_hook.read_text()
        assert "keep me" in content
        assert HOOK_MARKER not in content

    def test_uninstall_returns_false_if_not_found(self, git_repo):
        assert uninstall_hook(str(git_repo)) is False

    def test_is_hook_installed(self, git_repo):
        assert is_hook_installed(str(git_repo)) is False
        install_hook(str(git_repo))
        assert is_hook_installed(str(git_repo)) is True
        uninstall_hook(str(git_repo))
        assert is_hook_installed(str(git_repo)) is False


# --- Tests for snapshot with git metadata ---

class TestSnapshotGitMetadata:
    def test_snapshot_captures_git_context(self, store, git_repo):
        snap = create_snapshot(
            store, collectors=["envvars"], file_root=str(git_repo)
        )
        meta = snap.get("metadata", {})
        assert meta.get("git_commit") is not None
        assert len(meta["git_commit"]) == 40
        assert meta.get("git_branch") in ("main", "master")

    def test_snapshot_without_git(self, store, tmp_path):
        non_repo = tmp_path / "norepox"
        non_repo.mkdir()
        snap = create_snapshot(
            store, collectors=["envvars"], file_root=str(non_repo)
        )
        meta = snap.get("metadata", {})
        assert meta.get("git_commit") is None

    def test_snapshot_no_git_flag(self, store, git_repo):
        snap = create_snapshot(
            store, collectors=["envvars"], file_root=str(git_repo),
            include_git=False,
        )
        meta = snap.get("metadata", {})
        assert meta.get("git_commit") is None

    def test_snapshot_git_hook_auto_labels(self, store, git_repo):
        snap = create_snapshot(
            store, collectors=["envvars"], file_root=str(git_repo),
            git_hook=True,
        )
        assert snap["label"] is not None
        assert snap["label"].startswith("git:")


# --- Tests for git:<hash> reference resolution ---

class TestGitRefResolution:
    def test_find_by_full_hash(self, store, git_repo):
        snap = create_snapshot(
            store, collectors=["envvars"], file_root=str(git_repo),
        )
        meta = snap["metadata"]
        full_hash = meta["git_commit"]

        found = store.find_by_git_commit(full_hash)
        assert found is not None
        assert found["id"] == snap["id"]

    def test_find_by_short_hash(self, store, git_repo):
        snap = create_snapshot(
            store, collectors=["envvars"], file_root=str(git_repo),
        )
        meta = snap["metadata"]
        short_hash = meta["git_commit_short"]

        found = store.find_by_git_commit(short_hash)
        assert found is not None
        assert found["id"] == snap["id"]

    def test_find_by_prefix(self, store, git_repo):
        snap = create_snapshot(
            store, collectors=["envvars"], file_root=str(git_repo),
        )
        meta = snap["metadata"]
        prefix = meta["git_commit"][:10]

        found = store.find_by_git_commit(prefix)
        assert found is not None
        assert found["id"] == snap["id"]

    def test_returns_none_for_unknown_hash(self, store):
        found = store.find_by_git_commit("deadbeef1234567890")
        assert found is None


# --- CLI command tests ---

class TestHooksCLI:
    def test_hooks_install(self, runner, git_repo):
        result = runner.invoke(main, ["hooks", "install", "--repo", str(git_repo)])
        assert result.exit_code == 0
        assert "installed" in result.output.lower()

    def test_hooks_status_not_installed(self, runner, git_repo):
        result = runner.invoke(main, ["hooks", "status", "--repo", str(git_repo)])
        assert result.exit_code == 0
        assert "not installed" in result.output.lower()

    def test_hooks_status_installed(self, runner, git_repo):
        install_hook(str(git_repo))
        result = runner.invoke(main, ["hooks", "status", "--repo", str(git_repo)])
        assert result.exit_code == 0
        assert "installed" in result.output.lower()
        assert "not" not in result.output.lower()

    def test_hooks_uninstall(self, runner, git_repo):
        install_hook(str(git_repo))
        result = runner.invoke(main, ["hooks", "uninstall", "--repo", str(git_repo)])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()


class TestGitLogCLI:
    def test_gitlog_in_repo(self, runner, db_path, git_repo):
        # Create a snapshot with git context
        store = SnapshotStore(db_path)
        create_snapshot(store, collectors=["envvars"], file_root=str(git_repo))
        store.close()

        result = runner.invoke(
            main, ["--db", db_path, "gitlog", "--repo", str(git_repo)]
        )
        assert result.exit_code == 0
        assert "initial commit" in result.output


class TestDiffWithGitRef:
    def test_diff_git_ref(self, runner, db_path, git_repo):
        store = SnapshotStore(db_path)
        snap = create_snapshot(store, collectors=["envvars"], file_root=str(git_repo))
        commit_short = snap["metadata"]["git_commit_short"]
        store.close()

        # Diff git:<hash> against latest
        result = runner.invoke(
            main, ["--db", db_path, "diff", f"git:{commit_short}", "latest"]
        )
        assert result.exit_code == 0


class TestRunGit:
    def test_run_git_success(self, git_repo):
        result = _run_git(["rev-parse", "HEAD"], cwd=str(git_repo))
        assert result is not None
        assert len(result) == 40

    def test_run_git_failure(self, tmp_path):
        non_repo = tmp_path / "nope"
        non_repo.mkdir()
        result = _run_git(["rev-parse", "HEAD"], cwd=str(non_repo))
        assert result is None

    @mock.patch("strata.git_integration.subprocess.run")
    def test_run_git_handles_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        result = _run_git(["status"])
        assert result is None

    @mock.patch("strata.git_integration.subprocess.run")
    def test_run_git_handles_missing_binary(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        result = _run_git(["status"])
        assert result is None
