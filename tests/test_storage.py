"""Tests for the snapshot storage module."""

import tempfile
import time
from pathlib import Path

import pytest

from strata.storage import SnapshotStore


@pytest.fixture
def store(tmp_path):
    """Create a temporary store for testing."""
    db_path = tmp_path / "test.db"
    s = SnapshotStore(db_path)
    yield s
    s.close()


class TestSnapshotStore:
    def test_save_and_retrieve(self, store):
        data = {
            "envvars": {"HOME": "/home/user", "PATH": "/usr/bin"},
            "system": {"hostname": "test-host"},
        }
        snap_id = store.save_snapshot(data, label="test1", hostname="test-host")
        assert snap_id == 1

        snap = store.get_snapshot(snap_id)
        assert snap is not None
        assert snap["id"] == 1
        assert snap["label"] == "test1"
        assert snap["hostname"] == "test-host"
        assert snap["data"]["envvars"]["HOME"] == "/home/user"
        assert snap["data"]["system"]["hostname"] == "test-host"

    def test_get_nonexistent(self, store):
        assert store.get_snapshot(999) is None

    def test_list_snapshots(self, store):
        store.save_snapshot({"envvars": {"A": "1"}}, label="first")
        store.save_snapshot({"envvars": {"A": "2"}}, label="second")
        store.save_snapshot({"envvars": {"A": "3"}}, label="third")

        snapshots = store.list_snapshots(limit=10)
        assert len(snapshots) == 3
        # Most recent first
        assert snapshots[0]["label"] == "third"
        assert snapshots[2]["label"] == "first"

    def test_list_with_limit(self, store):
        for i in range(5):
            store.save_snapshot({"envvars": {"i": str(i)}}, label=f"snap{i}")

        snapshots = store.list_snapshots(limit=2)
        assert len(snapshots) == 2

    def test_find_by_label(self, store):
        store.save_snapshot({"envvars": {"A": "1"}}, label="baseline")
        store.save_snapshot({"envvars": {"A": "2"}}, label="deploy")

        snap = store.find_by_label("baseline")
        assert snap is not None
        assert snap["label"] == "baseline"
        assert snap["data"]["envvars"]["A"] == "1"

    def test_find_by_label_not_found(self, store):
        assert store.find_by_label("nonexistent") is None

    def test_delete_snapshot(self, store):
        snap_id = store.save_snapshot({"envvars": {"A": "1"}}, label="delete-me")
        assert store.get_snapshot(snap_id) is not None

        result = store.delete_snapshot(snap_id)
        assert result is True
        assert store.get_snapshot(snap_id) is None

    def test_delete_nonexistent(self, store):
        assert store.delete_snapshot(999) is False

    def test_count(self, store):
        assert store.count() == 0
        store.save_snapshot({"envvars": {}})
        assert store.count() == 1
        store.save_snapshot({"envvars": {}})
        assert store.count() == 2

    def test_search(self, store):
        store.save_snapshot(
            {"envvars": {"HOME": "/home/user", "PATH": "/usr/bin"}},
            label="snap1",
        )
        store.save_snapshot(
            {"envvars": {"HOME": "/root", "SHELL": "/bin/bash"}},
            label="snap2",
        )

        results = store.search("envvars", "HOME")
        assert len(results) == 2
        # Most recent first
        assert results[0]["value"] == "/root"
        assert results[1]["value"] == "/home/user"

    def test_search_no_results(self, store):
        store.save_snapshot({"envvars": {"HOME": "/home/user"}})
        results = store.search("envvars", "NONEXISTENT")
        assert len(results) == 0

    def test_metadata(self, store):
        metadata = {"collectors": ["envvars"], "errors": {"docker": "not found"}}
        snap_id = store.save_snapshot({"envvars": {}}, metadata=metadata)
        snap = store.get_snapshot(snap_id)
        assert snap["metadata"]["collectors"] == ["envvars"]
        assert snap["metadata"]["errors"]["docker"] == "not found"

    def test_get_latest(self, store):
        store.save_snapshot({"envvars": {"v": "1"}}, label="old")
        store.save_snapshot({"envvars": {"v": "2"}}, label="new")

        latest = store.get_latest(1)
        assert len(latest) == 1
        assert latest[0]["label"] == "new"
