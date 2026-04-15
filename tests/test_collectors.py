"""Tests for the collectors."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from strata.collectors.envvars import EnvVarsCollector, _is_sensitive, _mask
from strata.collectors.processes import ProcessCollector
from strata.collectors.network import NetworkCollector, _hex_to_ip_port
from strata.collectors.files import FileCollector
from strata.collectors.disk import DiskCollector
from strata.collectors.system import SystemCollector
from strata.collectors.packages import PackageCollector
from strata.collectors.docker import DockerCollector


class TestEnvVars:
    def test_collect_returns_dict(self):
        collector = EnvVarsCollector()
        result = collector.collect()
        assert isinstance(result, dict)
        # Should have some env vars
        assert len(result) > 0

    def test_sensitive_detection(self):
        assert _is_sensitive("API_KEY") is True
        assert _is_sensitive("DATABASE_PASSWORD") is True
        assert _is_sensitive("AWS_SECRET_ACCESS_KEY") is True
        assert _is_sensitive("HOME") is False
        assert _is_sensitive("PATH") is False

    def test_masking(self):
        assert _mask("abc") == "****"
        assert _mask("abcdefgh") == "ab****gh"
        # Short values fully masked
        assert _mask("ab") == "****"

    def test_sensitive_vars_masked(self):
        with patch.dict(os.environ, {"TEST_API_KEY": "super-secret-123"}):
            collector = EnvVarsCollector()
            result = collector.collect()
            if "TEST_API_KEY" in result:
                assert "super-secret-123" not in result["TEST_API_KEY"]
                assert "****" in result["TEST_API_KEY"]

    def test_diff_entry_sensitive(self):
        desc = EnvVarsCollector.diff_entry("API_KEY", "old", "new")
        assert "masked" in desc.lower()

    def test_diff_entry_normal(self):
        desc = EnvVarsCollector.diff_entry("HOME", "/old", "/new")
        assert "/old" in desc
        assert "/new" in desc


class TestProcesses:
    def test_collect_returns_dict(self):
        collector = ProcessCollector()
        result = collector.collect()
        assert isinstance(result, dict)

    def test_diff_entry_started(self):
        desc = ProcessCollector.diff_entry(
            "python|python test.py",
            None,
            {"pid": 1234, "name": "python", "cmdline": "python test.py"},
        )
        assert "1234" in desc
        assert "+" in desc

    def test_diff_entry_stopped(self):
        desc = ProcessCollector.diff_entry(
            "python|python test.py",
            {"pid": 1234, "name": "python", "cmdline": "python test.py"},
            None,
        )
        assert "stopped" in desc


class TestNetwork:
    def test_hex_to_ip_port_ipv4(self):
        # 127.0.0.1:8080 => 0100007F:1F90
        ip, port = _hex_to_ip_port("0100007F:1F90")
        assert ip == "127.0.0.1"
        assert port == 8080

    def test_hex_to_ip_port_any(self):
        ip, port = _hex_to_ip_port("00000000:0050")
        assert ip == "0.0.0.0"
        assert port == 80

    def test_collect_returns_dict(self):
        collector = NetworkCollector()
        result = collector.collect()
        assert isinstance(result, dict)

    def test_diff_entry_new_listener(self):
        desc = NetworkCollector.diff_entry(
            "tcp:0.0.0.0:8080",
            None,
            {"protocol": "tcp", "port": 8080},
        )
        assert "8080" in desc
        assert "+" in desc


class TestFiles:
    def test_collect_in_temp_dir(self, tmp_path):
        # Create some test files
        (tmp_path / "config.json").write_text('{"key": "value"}')
        (tmp_path / "app.yaml").write_text("name: test")
        (tmp_path / "random.txt").write_text("not watched")

        collector = FileCollector(root=str(tmp_path))
        result = collector.collect()

        assert "config.json" in result
        assert "app.yaml" in result
        assert "random.txt" not in result  # .txt not in watch patterns

    def test_file_info_has_hash(self, tmp_path):
        (tmp_path / "test.json").write_text('{"a": 1}')
        collector = FileCollector(root=str(tmp_path))
        result = collector.collect()
        assert "test.json" in result
        assert "sha256" in result["test.json"]
        assert "size" in result["test.json"]

    def test_detects_changes(self, tmp_path):
        f = tmp_path / "config.toml"
        f.write_text("[section]\nkey = 1")

        collector = FileCollector(root=str(tmp_path))
        result1 = collector.collect()
        hash1 = result1["config.toml"]["sha256"]

        f.write_text("[section]\nkey = 2")
        result2 = collector.collect()
        hash2 = result2["config.toml"]["sha256"]

        assert hash1 != hash2

    def test_skips_hidden_dirs(self, tmp_path):
        hidden = tmp_path / ".git"
        hidden.mkdir()
        (hidden / "config.json").write_text("{}")

        collector = FileCollector(root=str(tmp_path))
        result = collector.collect()
        assert not any(".git" in k for k in result)

    def test_diff_entry_new_file(self):
        desc = FileCollector.diff_entry("config.json", None, {"size": 100})
        assert "new file" in desc
        assert "+" in desc

    def test_diff_entry_deleted(self):
        desc = FileCollector.diff_entry("config.json", {"size": 100}, None)
        assert "deleted" in desc


class TestDisk:
    def test_collect_returns_dict(self):
        collector = DiskCollector()
        result = collector.collect()
        assert isinstance(result, dict)
        # Should have at least root
        assert len(result) > 0

    def test_has_usage_fields(self):
        collector = DiskCollector()
        result = collector.collect()
        for mount, info in result.items():
            assert "total_gb" in info
            assert "used_gb" in info
            assert "free_gb" in info
            assert "percent_used" in info


class TestSystem:
    def test_collect_returns_dict(self):
        collector = SystemCollector()
        result = collector.collect()
        assert isinstance(result, dict)
        assert "hostname" in result
        assert "platform" in result
        assert "python" in result
        assert "timestamp" in result

    def test_has_memory_info(self):
        collector = SystemCollector()
        result = collector.collect()
        if "memory" in result:
            mem = result["memory"]
            assert "total_mb" in mem
            assert "available_mb" in mem


class TestPackages:
    def test_collect_returns_dict(self):
        collector = PackageCollector()
        result = collector.collect()
        assert isinstance(result, dict)
        # runtimes sub-dict should exist and contain git or python3
        runtimes = result.get("runtimes", result)
        assert "python3" in runtimes or "git" in runtimes

    def test_diff_entry_installed(self):
        desc = PackageCollector.diff_entry("node", None, "v18.0.0")
        assert "installed" in desc

    def test_diff_entry_removed(self):
        desc = PackageCollector.diff_entry("node", "v18.0.0", None)
        assert "no longer found" in desc

    def test_diff_entry_changed(self):
        desc = PackageCollector.diff_entry("node", "v16.0.0", "v18.0.0")
        assert "v16.0.0" in desc
        assert "v18.0.0" in desc


class TestDocker:
    def test_is_available_returns_bool(self):
        result = DockerCollector.is_available()
        assert isinstance(result, bool)

    def test_collect_returns_dict(self):
        collector = DockerCollector()
        result = collector.collect()
        assert isinstance(result, dict)
