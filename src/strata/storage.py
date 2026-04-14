"""SQLite-based snapshot storage."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path.home() / ".strata" / "strata.db"


class SnapshotStore:
    """Stores and retrieves environment snapshots using SQLite."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT,
                timestamp REAL NOT NULL,
                hostname TEXT,
                metadata TEXT
            );

            CREATE TABLE IF NOT EXISTS snapshot_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                collector TEXT NOT NULL,
                data TEXT NOT NULL,
                FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                ON snapshots(timestamp);
            CREATE INDEX IF NOT EXISTS idx_snapshots_label
                ON snapshots(label);
            CREATE INDEX IF NOT EXISTS idx_snapshot_data_snapshot_id
                ON snapshot_data(snapshot_id);
        """)
        self._conn.commit()

    def save_snapshot(
        self,
        data: dict[str, dict[str, Any]],
        label: str | None = None,
        hostname: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Save a snapshot and return its ID.

        Args:
            data: Dict mapping collector name -> collected data dict.
            label: Optional human-readable label.
            hostname: Optional hostname.
            metadata: Optional extra metadata.

        Returns:
            The snapshot ID.
        """
        timestamp = time.time()
        cursor = self._conn.execute(
            "INSERT INTO snapshots (label, timestamp, hostname, metadata) VALUES (?, ?, ?, ?)",
            (label, timestamp, hostname, json.dumps(metadata or {})),
        )
        snapshot_id = cursor.lastrowid

        for collector_name, collector_data in data.items():
            self._conn.execute(
                "INSERT INTO snapshot_data (snapshot_id, collector, data) VALUES (?, ?, ?)",
                (snapshot_id, collector_name, json.dumps(collector_data)),
            )

        self._conn.commit()
        return snapshot_id

    def get_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        """Retrieve a snapshot by ID."""
        row = self._conn.execute(
            "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        if not row:
            return None

        data_rows = self._conn.execute(
            "SELECT collector, data FROM snapshot_data WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()

        return {
            "id": row["id"],
            "label": row["label"],
            "timestamp": row["timestamp"],
            "hostname": row["hostname"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "data": {r["collector"]: json.loads(r["data"]) for r in data_rows},
        }

    def get_latest(self, n: int = 1) -> list[dict[str, Any]]:
        """Get the N most recent snapshots (metadata only, no data)."""
        rows = self._conn.execute(
            "SELECT id, label, timestamp, hostname, metadata FROM snapshots ORDER BY timestamp DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "label": r["label"],
                "timestamp": r["timestamp"],
                "hostname": r["hostname"],
                "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
            }
            for r in rows
        ]

    def list_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        """List snapshots (metadata only)."""
        return self.get_latest(limit)

    def find_by_label(self, label: str) -> dict[str, Any] | None:
        """Find a snapshot by label."""
        row = self._conn.execute(
            "SELECT id FROM snapshots WHERE label = ? ORDER BY timestamp DESC LIMIT 1",
            (label,),
        ).fetchone()
        if row:
            return self.get_snapshot(row["id"])
        return None

    def delete_snapshot(self, snapshot_id: int) -> bool:
        """Delete a snapshot by ID."""
        self._conn.execute("DELETE FROM snapshot_data WHERE snapshot_id = ?", (snapshot_id,))
        cursor = self._conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def count(self) -> int:
        """Return total number of snapshots."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM snapshots").fetchone()
        return row["cnt"]

    def search(self, collector: str, key_pattern: str) -> list[dict[str, Any]]:
        """Search across snapshots for a specific key in a collector's data.

        Returns snapshots that contain a matching key, with the matched values.
        """
        rows = self._conn.execute(
            """
            SELECT s.id, s.label, s.timestamp, sd.data
            FROM snapshots s
            JOIN snapshot_data sd ON sd.snapshot_id = s.id
            WHERE sd.collector = ?
            ORDER BY s.timestamp DESC
            LIMIT 50
            """,
            (collector,),
        ).fetchall()

        results = []
        for row in rows:
            data = json.loads(row["data"])
            for key, value in data.items():
                if key_pattern.lower() in key.lower():
                    results.append({
                        "snapshot_id": row["id"],
                        "label": row["label"],
                        "timestamp": row["timestamp"],
                        "key": key,
                        "value": value,
                    })
        return results

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
