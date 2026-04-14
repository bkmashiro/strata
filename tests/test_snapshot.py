"""Tests for snapshot creation."""

import pytest

from strata.storage import SnapshotStore
from strata.snapshot import create_snapshot


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = SnapshotStore(db_path)
    yield s
    s.close()


class TestCreateSnapshot:
    def test_creates_snapshot(self, store):
        snap = create_snapshot(store)
        assert snap is not None
        assert "id" in snap
        assert "data" in snap
        assert snap["id"] == 1

    def test_with_label(self, store):
        snap = create_snapshot(store, label="my-baseline")
        assert snap["label"] == "my-baseline"

    def test_with_collector_filter(self, store):
        snap = create_snapshot(store, collectors=["envvars", "system"])
        assert "envvars" in snap["data"]
        assert "system" in snap["data"]
        assert "processes" not in snap["data"]

    def test_multiple_snapshots(self, store):
        snap1 = create_snapshot(store, label="first")
        snap2 = create_snapshot(store, label="second")
        assert snap1["id"] != snap2["id"]
        assert store.count() == 2

    def test_has_metadata(self, store):
        snap = create_snapshot(store)
        assert "metadata" in snap
        assert "collectors" in snap["metadata"]
        assert len(snap["metadata"]["collectors"]) > 0

    def test_file_root(self, store, tmp_path):
        config = tmp_path / "config.json"
        config.write_text('{"key": "value"}')

        snap = create_snapshot(store, collectors=["files"], file_root=str(tmp_path))
        assert "files" in snap["data"]
