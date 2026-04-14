"""Environment variables collector."""

from __future__ import annotations

import os
from typing import Any

from strata.collectors.base import Collector

# Variables to exclude (sensitive or too noisy)
_EXCLUDED_PREFIXES = (
    "LS_COLORS",
    "LESS_TERMCAP",
)

_SENSITIVE_PATTERNS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "KEY",
    "CREDENTIAL",
    "PRIVATE",
)


def _is_sensitive(name: str) -> bool:
    upper = name.upper()
    return any(pat in upper for pat in _SENSITIVE_PATTERNS)


def _mask(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


class EnvVarsCollector(Collector):
    """Collects current environment variables."""

    name = "envvars"

    def collect(self) -> dict[str, Any]:
        result = {}
        for key, value in sorted(os.environ.items()):
            if key.startswith(_EXCLUDED_PREFIXES):
                continue
            if _is_sensitive(key):
                result[key] = _mask(value)
            else:
                result[key] = value
        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if _is_sensitive(key):
            return f"{key}: [masked value changed]"
        return f"{key}: {old!r} -> {new!r}"
