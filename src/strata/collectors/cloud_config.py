"""Cloud CLI configuration collector (no secrets)."""

from __future__ import annotations

import configparser
import json
import subprocess
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector


def _collect_aws_config() -> dict[str, Any] | None:
    """Collect AWS CLI config profiles and regions (NOT credentials)."""
    config_path = Path.home() / ".aws" / "config"
    if not config_path.is_file():
        return None

    try:
        parser = configparser.ConfigParser()
        parser.read(str(config_path))

        profiles = {}
        for section in parser.sections():
            profile_name = section.replace("profile ", "")
            profile_data = {}
            # Only collect non-sensitive fields
            for safe_key in ("region", "output", "sso_start_url", "sso_region",
                             "sso_account_id", "sso_role_name"):
                if parser.has_option(section, safe_key):
                    profile_data[safe_key] = parser.get(section, safe_key)
            if profile_data:
                profiles[profile_name] = profile_data

        return profiles if profiles else None
    except (OSError, configparser.Error):
        return None


def _collect_gcp_config() -> dict[str, Any] | None:
    """Collect GCP active config (account, project, region)."""
    gcloud_dir = Path.home() / ".config" / "gcloud"
    if not gcloud_dir.is_dir():
        return None

    result = {}

    # Read active config properties
    props_path = gcloud_dir / "properties"
    if props_path.is_file():
        try:
            parser = configparser.ConfigParser()
            parser.read(str(props_path))
            if parser.has_option("core", "account"):
                result["account"] = parser.get("core", "account")
            if parser.has_option("core", "project"):
                result["project"] = parser.get("core", "project")
            if parser.has_option("compute", "region"):
                result["region"] = parser.get("compute", "region")
            if parser.has_option("compute", "zone"):
                result["zone"] = parser.get("compute", "zone")
        except (OSError, configparser.Error):
            pass

    # Read active configuration name
    active_config = gcloud_dir / "active_config"
    if active_config.is_file():
        try:
            result["active_config"] = active_config.read_text().strip()
        except OSError:
            pass

    return result if result else None


def _collect_azure_config() -> dict[str, Any] | None:
    """Collect Azure active subscription info."""
    try:
        proc = subprocess.run(
            ["az", "account", "show", "--output", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        return {
            "subscription_name": data.get("name", ""),
            "subscription_id": data.get("id", ""),
            "tenant_id": data.get("tenantId", ""),
            "state": data.get("state", ""),
            "user": data.get("user", {}).get("name", ""),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None


def _collect_kube_config() -> dict[str, Any] | None:
    """Collect Kubernetes contexts and current context (no certs/keys)."""
    kube_config = Path.home() / ".kube" / "config"
    if not kube_config.is_file():
        return None

    try:
        # Use PyYAML if available, otherwise parse with kubectl
        try:
            import yaml
            with open(kube_config) as f:
                config = yaml.safe_load(f)

            result = {}
            current_ctx = config.get("current-context", "")
            if current_ctx:
                result["current_context"] = current_ctx

            contexts = []
            for ctx in config.get("contexts", []):
                ctx_info = {"name": ctx.get("name", "")}
                context_data = ctx.get("context", {})
                if context_data.get("cluster"):
                    ctx_info["cluster"] = context_data["cluster"]
                if context_data.get("namespace"):
                    ctx_info["namespace"] = context_data["namespace"]
                contexts.append(ctx_info)

            if contexts:
                result["contexts"] = contexts
            return result if result else None

        except ImportError:
            # Fall back to kubectl
            proc = subprocess.run(
                ["kubectl", "config", "get-contexts", "--no-headers", "-o", "name"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode != 0:
                return None

            contexts = [c.strip() for c in proc.stdout.strip().split("\n") if c.strip()]

            current_proc = subprocess.run(
                ["kubectl", "config", "current-context"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            current_ctx = current_proc.stdout.strip() if current_proc.returncode == 0 else ""

            result = {}
            if current_ctx:
                result["current_context"] = current_ctx
            if contexts:
                result["contexts"] = [{"name": c} for c in contexts]
            return result if result else None

    except (OSError, PermissionError, Exception):
        return None


class CloudConfigCollector(Collector):
    """Collects cloud CLI configurations (no secrets)."""

    name = "cloud_config"

    def collect(self) -> dict[str, Any]:
        result: dict[str, Any] = {}

        aws = _collect_aws_config()
        if aws:
            result["aws"] = aws

        gcp = _collect_gcp_config()
        if gcp:
            result["gcp"] = gcp

        azure = _collect_azure_config()
        if azure:
            result["azure"] = azure

        kube = _collect_kube_config()
        if kube:
            result["kubernetes"] = kube

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if old is None:
            return f"+ {key}: cloud config detected"
        if new is None:
            return f"- {key}: cloud config no longer found"
        return f"  {key}: configuration changed"
