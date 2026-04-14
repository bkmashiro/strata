"""Base collector interface."""

from __future__ import annotations

import abc
from typing import Any


class Collector(abc.ABC):
    """Base class for environment state collectors."""

    # Human-readable name for this collector
    name: str = "base"

    @abc.abstractmethod
    def collect(self) -> dict[str, Any]:
        """Collect environment state and return as a dictionary.

        Returns:
            Dictionary mapping item keys to their current values.
            Keys should be stable identifiers (e.g., "PATH", "pid:1234").
            Values should be JSON-serializable.
        """
        ...

    @classmethod
    def is_available(cls) -> bool:
        """Check if this collector can run in the current environment."""
        return True

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        """Format a single diff entry for display.

        Override this for custom diff formatting per collector.
        """
        return f"{key}: {old!r} -> {new!r}"
