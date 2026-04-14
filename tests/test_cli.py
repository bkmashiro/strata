"""Tests for the CLI interface."""

import pytest
from click.testing import CliRunner

from strata.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestCLI:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "strata" in result.output.lower()

    def test_snap(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "snap"])
        assert result.exit_code == 0
        assert "Snapshot #1 saved" in result.output

    def test_snap_with_label(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "snap", "-l", "test-label"])
        assert result.exit_code == 0
        assert "test-label" in result.output

    def test_snap_with_collectors(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "snap", "-c", "envvars", "-c", "system"])
        assert result.exit_code == 0
        assert "Snapshot #1 saved" in result.output

    def test_ls_empty(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "ls"])
        assert result.exit_code == 0
        assert "No snapshots found" in result.output

    def test_ls_with_snapshots(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap", "-l", "first"])
        runner.invoke(main, ["--db", db_path, "snap", "-l", "second"])
        result = runner.invoke(main, ["--db", db_path, "ls"])
        assert result.exit_code == 0
        assert "first" in result.output
        assert "second" in result.output

    def test_show(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap", "-l", "mysnap"])
        result = runner.invoke(main, ["--db", db_path, "show", "1"])
        assert result.exit_code == 0
        assert "mysnap" in result.output

    def test_show_latest(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap", "-l", "latest-snap"])
        result = runner.invoke(main, ["--db", db_path, "show", "latest"])
        assert result.exit_code == 0
        assert "latest-snap" in result.output

    def test_show_by_label(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap", "-l", "deploy-v2"])
        result = runner.invoke(main, ["--db", db_path, "show", "deploy-v2"])
        assert result.exit_code == 0

    def test_show_not_found(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "show", "999"])
        assert result.exit_code != 0

    def test_show_collector_detail(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap"])
        result = runner.invoke(main, ["--db", db_path, "show", "1", "-c", "envvars"])
        assert result.exit_code == 0

    def test_diff(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap", "-l", "before"])
        runner.invoke(main, ["--db", db_path, "snap", "-l", "after"])
        result = runner.invoke(main, ["--db", db_path, "diff", "1", "2"])
        assert result.exit_code == 0

    def test_diff_with_latest(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap", "-l", "old"])
        runner.invoke(main, ["--db", db_path, "snap", "-l", "new"])
        result = runner.invoke(main, ["--db", db_path, "diff", "1", "latest"])
        assert result.exit_code == 0

    def test_diff_not_found(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "diff", "1", "2"])
        assert result.exit_code != 0

    def test_rm(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap", "-l", "delete-me"])
        result = runner.invoke(main, ["--db", db_path, "rm", "1"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_rm_not_found(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "rm", "999"])
        assert result.exit_code != 0

    def test_search(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "snap"])
        result = runner.invoke(main, ["--db", db_path, "search", "envvars", "HOME"])
        assert result.exit_code == 0

    def test_doctor_creates_baseline(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "doctor"])
        assert result.exit_code == 0
        assert "baseline" in result.output.lower()

    def test_doctor_compares(self, runner, db_path):
        runner.invoke(main, ["--db", db_path, "doctor"])
        result = runner.invoke(main, ["--db", db_path, "doctor"])
        assert result.exit_code == 0
        assert "baseline" in result.output.lower()

    def test_status(self, runner, db_path):
        result = runner.invoke(main, ["--db", db_path, "status"])
        assert result.exit_code == 0
        assert "Strata" in result.output
        assert "Snapshots" in result.output
