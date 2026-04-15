"""Package/runtime version collector with installed package sub-collectors."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from strata.collectors.base import Collector

# Commands to check for runtime versions
_VERSION_COMMANDS = [
    ("node", ["node", "--version"]),
    ("npm", ["npm", "--version"]),
    ("python3", ["python3", "--version"]),
    ("pip", ["pip3", "--version"]),
    ("ruby", ["ruby", "--version"]),
    ("go", ["go", "version"]),
    ("rustc", ["rustc", "--version"]),
    ("cargo", ["cargo", "--version"]),
    ("java", ["java", "-version"]),  # outputs to stderr
    ("gcc", ["gcc", "--version"]),
    ("git", ["git", "--version"]),
    ("docker", ["docker", "--version"]),
    ("kubectl", ["kubectl", "version", "--client", "--short"]),
    ("terraform", ["terraform", "--version"]),
]

# Maximum packages to collect per package manager
_MAX_PACKAGES = 500


def _get_version(cmd: list[str]) -> str | None:
    """Run a version command and return the first line of output."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = proc.stdout.strip() or proc.stderr.strip()
        if output:
            return output.split("\n")[0].strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _run_cmd(cmd: list[str], timeout: int = 15) -> str | None:
    """Run a command and return stdout, or None on failure."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _collect_pip() -> dict[str, str] | None:
    """Collect pip installed packages."""
    output = _run_cmd(["pip3", "list", "--format=json"])
    if not output:
        output = _run_cmd(["pip", "list", "--format=json"])
    if not output:
        return None
    try:
        packages = json.loads(output)
        result = {}
        for pkg in packages[:_MAX_PACKAGES]:
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            if name:
                result[name] = version
        return result if result else None
    except (json.JSONDecodeError, KeyError):
        return None


def _collect_npm_global() -> dict[str, str] | None:
    """Collect globally installed npm packages."""
    output = _run_cmd(["npm", "list", "-g", "--depth=0", "--json"])
    if not output:
        return None
    try:
        data = json.loads(output)
        deps = data.get("dependencies", {})
        result = {}
        for name, info in list(deps.items())[:_MAX_PACKAGES]:
            version = info.get("version", "unknown") if isinstance(info, dict) else str(info)
            result[name] = version
        return result if result else None
    except (json.JSONDecodeError, KeyError):
        return None


def _collect_cargo() -> dict[str, str] | None:
    """Collect cargo installed packages."""
    output = _run_cmd(["cargo", "install", "--list"])
    if not output:
        return None
    result = {}
    current_pkg = None
    for line in output.split("\n"):
        if not line.startswith(" ") and line.strip():
            # Package line: "ripgrep v14.0.0:"
            parts = line.strip().rstrip(":").split()
            if len(parts) >= 2:
                name = parts[0]
                version = parts[1].lstrip("v")
                result[name] = version
                current_pkg = name
        if len(result) >= _MAX_PACKAGES:
            break
    return result if result else None


def _collect_gem() -> dict[str, str] | None:
    """Collect gem installed packages."""
    output = _run_cmd(["gem", "list", "--no-verbose"])
    if not output:
        return None
    result = {}
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Format: "name (version1, version2)"
        if "(" in line and ")" in line:
            name = line[:line.index("(")].strip()
            versions = line[line.index("(") + 1:line.index(")")].strip()
            # Take the first (latest) version
            version = versions.split(",")[0].strip()
            if name:
                result[name] = version
        if len(result) >= _MAX_PACKAGES:
            break
    return result if result else None


def _collect_brew() -> dict[str, str] | None:
    """Collect brew installed packages."""
    output = _run_cmd(["brew", "list", "--versions"], timeout=30)
    if not output:
        return None
    result = {}
    for line in output.split("\n"):
        parts = line.strip().split()
        if len(parts) >= 2:
            name = parts[0]
            version = parts[-1]  # Take latest version
            result[name] = version
        if len(result) >= _MAX_PACKAGES:
            break
    return result if result else None


def _collect_apt() -> dict[str, str] | None:
    """Collect apt/dpkg installed packages."""
    output = _run_cmd(
        ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
        timeout=30,
    )
    if not output:
        return None
    result = {}
    for line in output.split("\n"):
        parts = line.strip().split("\t")
        if len(parts) == 2:
            result[parts[0]] = parts[1]
        if len(result) >= _MAX_PACKAGES:
            break
    return result if result else None


def _collect_conda() -> dict[str, str] | None:
    """Collect conda installed packages."""
    output = _run_cmd(["conda", "list", "--json"], timeout=30)
    if not output:
        return None
    try:
        packages = json.loads(output)
        result = {}
        for pkg in packages[:_MAX_PACKAGES]:
            name = pkg.get("name", "")
            version = pkg.get("version", "")
            if name:
                result[name] = version
        return result if result else None
    except (json.JSONDecodeError, KeyError):
        return None


def _collect_pipx() -> dict[str, str] | None:
    """Collect pipx installed packages."""
    output = _run_cmd(["pipx", "list", "--json"])
    if not output:
        return None
    try:
        data = json.loads(output)
        venvs = data.get("venvs", {})
        result = {}
        for name, info in list(venvs.items())[:_MAX_PACKAGES]:
            metadata = info.get("metadata", {}).get("main_package", {})
            version = metadata.get("package_version", "unknown")
            result[name] = version
        return result if result else None
    except (json.JSONDecodeError, KeyError):
        return None


def _collect_yarn_global() -> dict[str, str] | None:
    """Collect yarn globally installed packages."""
    output = _run_cmd(["yarn", "global", "list", "--json"])
    if not output:
        return None
    result = {}
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get("type") == "info":
                # Parse "package@version" from the data field
                info_data = data.get("data", "")
                if "@" in info_data and '"' in info_data:
                    # Format: '"pkg@version" has binaries'
                    pkg_part = info_data.split('"')[1] if '"' in info_data else info_data
                    if "@" in pkg_part:
                        at_idx = pkg_part.rfind("@")
                        name = pkg_part[:at_idx]
                        version = pkg_part[at_idx + 1:]
                        if name:
                            result[name] = version
        except json.JSONDecodeError:
            continue
        if len(result) >= _MAX_PACKAGES:
            break
    return result if result else None


# Sub-collectors: (key_name, collector_function)
_PACKAGE_SUBCOLLECTORS = [
    ("pip", _collect_pip),
    ("npm_global", _collect_npm_global),
    ("cargo", _collect_cargo),
    ("gem", _collect_gem),
    ("brew", _collect_brew),
    ("apt", _collect_apt),
    ("conda", _collect_conda),
    ("pipx", _collect_pipx),
    ("yarn_global", _collect_yarn_global),
]


class PackageCollector(Collector):
    """Collects installed package/runtime versions and package manager inventories."""

    name = "packages"

    def collect(self) -> dict[str, Any]:
        result: dict[str, Any] = {}

        # Collect runtime versions
        runtimes = {}
        for name, cmd in _VERSION_COMMANDS:
            version = _get_version(cmd)
            if version:
                runtimes[name] = version
        if runtimes:
            result["runtimes"] = runtimes

        # Collect installed packages from each package manager
        for key, collector_fn in _PACKAGE_SUBCOLLECTORS:
            try:
                packages = collector_fn()
                if packages:
                    result[key] = packages
            except Exception:
                pass

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if old is None:
            if isinstance(new, dict):
                return f"+ {key}: {len(new)} packages detected"
            return f"+ {key}: installed ({new})"
        if new is None:
            if isinstance(old, dict):
                return f"- {key}: no longer found ({len(old)} packages)"
            return f"- {key}: no longer found"
        if isinstance(old, dict) and isinstance(new, dict):
            added = len(set(new.keys()) - set(old.keys()))
            removed = len(set(old.keys()) - set(new.keys()))
            changed = sum(1 for k in set(old.keys()) & set(new.keys()) if old[k] != new[k])
            parts = []
            if added:
                parts.append(f"+{added}")
            if removed:
                parts.append(f"-{removed}")
            if changed:
                parts.append(f"~{changed}")
            return f"  {key}: {' '.join(parts)} packages"
        return f"  {key}: {old} -> {new}"
