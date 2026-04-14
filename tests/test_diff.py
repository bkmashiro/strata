"""Tests for the diff module."""

import pytest

from strata.diff import diff_dicts, diff_snapshots, format_diff, summarize_diff


class TestDiffDicts:
    def test_identical(self):
        d = {"a": 1, "b": 2}
        assert diff_dicts(d, d) == {}

    def test_added(self):
        old = {"a": 1}
        new = {"a": 1, "b": 2}
        result = diff_dicts(old, new)
        assert result == {"b": (None, 2)}

    def test_removed(self):
        old = {"a": 1, "b": 2}
        new = {"a": 1}
        result = diff_dicts(old, new)
        assert result == {"b": (2, None)}

    def test_changed(self):
        old = {"a": 1}
        new = {"a": 2}
        result = diff_dicts(old, new)
        assert result == {"a": (1, 2)}

    def test_mixed(self):
        old = {"a": 1, "b": 2, "c": 3}
        new = {"a": 1, "b": 99, "d": 4}
        result = diff_dicts(old, new)
        assert "a" not in result  # unchanged
        assert result["b"] == (2, 99)  # changed
        assert result["c"] == (3, None)  # removed
        assert result["d"] == (None, 4)  # added

    def test_empty(self):
        assert diff_dicts({}, {}) == {}

    def test_all_new(self):
        result = diff_dicts({}, {"a": 1, "b": 2})
        assert result == {"a": (None, 1), "b": (None, 2)}

    def test_all_removed(self):
        result = diff_dicts({"a": 1, "b": 2}, {})
        assert result == {"a": (1, None), "b": (2, None)}


class TestDiffSnapshots:
    def _make_snap(self, data, snap_id=1, label=None):
        return {
            "id": snap_id,
            "label": label,
            "timestamp": 1000.0 + snap_id,
            "hostname": "test",
            "metadata": {},
            "data": data,
        }

    def test_no_changes(self):
        data = {"envvars": {"HOME": "/home/user"}}
        old = self._make_snap(data, 1)
        new = self._make_snap(data, 2)
        result = diff_snapshots(old, new)
        assert result == {}

    def test_envvar_changed(self):
        old = self._make_snap({"envvars": {"PATH": "/usr/bin"}}, 1)
        new = self._make_snap({"envvars": {"PATH": "/usr/local/bin:/usr/bin"}}, 2)
        result = diff_snapshots(old, new)
        assert "envvars" in result
        assert "PATH" in result["envvars"]
        assert result["envvars"]["PATH"] == ("/usr/bin", "/usr/local/bin:/usr/bin")

    def test_collector_filter(self):
        old = self._make_snap({
            "envvars": {"A": "1"},
            "system": {"hostname": "old"},
        }, 1)
        new = self._make_snap({
            "envvars": {"A": "2"},
            "system": {"hostname": "new"},
        }, 2)
        result = diff_snapshots(old, new, collectors=["envvars"])
        assert "envvars" in result
        assert "system" not in result

    def test_new_collector(self):
        old = self._make_snap({"envvars": {"A": "1"}}, 1)
        new = self._make_snap({
            "envvars": {"A": "1"},
            "docker": {"web": {"image": "nginx"}},
        }, 2)
        result = diff_snapshots(old, new)
        assert "docker" in result
        assert "envvars" not in result  # unchanged

    def test_removed_collector(self):
        old = self._make_snap({
            "envvars": {"A": "1"},
            "docker": {"web": {"image": "nginx"}},
        }, 1)
        new = self._make_snap({"envvars": {"A": "1"}}, 2)
        result = diff_snapshots(old, new)
        assert "docker" in result
        assert result["docker"]["web"] == ({"image": "nginx"}, None)


class TestFormatDiff:
    def test_format_entries(self):
        diff_result = {
            "envvars": {
                "NEW_VAR": (None, "hello"),
                "OLD_VAR": ("bye", None),
                "CHANGED": ("a", "b"),
            }
        }
        entries = format_diff(diff_result)
        assert len(entries) == 3

        types = {e["key"]: e["change_type"] for e in entries}
        assert types["NEW_VAR"] == "added"
        assert types["OLD_VAR"] == "removed"
        assert types["CHANGED"] == "changed"

    def test_empty_diff(self):
        assert format_diff({}) == []


class TestSummarizeDiff:
    def test_summary(self):
        diff_result = {
            "envvars": {
                "A": (None, "1"),
                "B": ("x", None),
                "C": ("1", "2"),
                "D": ("a", "b"),
            },
            "disk": {
                "/": ({"pct": 50}, {"pct": 60}),
            },
        }
        summary = summarize_diff(diff_result)
        assert summary["envvars"]["added"] == 1
        assert summary["envvars"]["removed"] == 1
        assert summary["envvars"]["changed"] == 2
        assert summary["disk"]["changed"] == 1

    def test_empty(self):
        assert summarize_diff({}) == {}
