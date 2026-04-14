"""Network listeners and connections collector."""

from __future__ import annotations

import re
import struct
import socket
from pathlib import Path
from typing import Any

from strata.collectors.base import Collector


def _hex_to_ip_port(hex_addr: str) -> tuple[str, int]:
    """Convert hex address:port from /proc/net/* to human-readable form."""
    ip_hex, port_hex = hex_addr.split(":")
    port = int(port_hex, 16)

    if len(ip_hex) == 8:  # IPv4
        ip_int = int(ip_hex, 16)
        ip_bytes = struct.pack("<I", ip_int)
        ip = socket.inet_ntoa(ip_bytes)
    else:
        ip = ip_hex  # Leave IPv6 as-is for simplicity
    return ip, port


_TCP_STATES = {
    "01": "ESTABLISHED",
    "02": "SYN_SENT",
    "03": "SYN_RECV",
    "04": "FIN_WAIT1",
    "05": "FIN_WAIT2",
    "06": "TIME_WAIT",
    "07": "CLOSE",
    "08": "CLOSE_WAIT",
    "09": "LAST_ACK",
    "0A": "LISTEN",
    "0B": "CLOSING",
}


def _parse_net_file(path: str) -> list[dict[str, Any]]:
    """Parse /proc/net/tcp or /proc/net/tcp6."""
    results = []
    try:
        content = Path(path).read_text()
    except (FileNotFoundError, PermissionError):
        return results

    for line in content.strip().split("\n")[1:]:  # Skip header
        parts = line.split()
        if len(parts) < 4:
            continue

        local_ip, local_port = _hex_to_ip_port(parts[1])
        remote_ip, remote_port = _hex_to_ip_port(parts[2])
        state = _TCP_STATES.get(parts[3], parts[3])

        results.append({
            "local_addr": f"{local_ip}:{local_port}",
            "remote_addr": f"{remote_ip}:{remote_port}",
            "state": state,
            "local_port": local_port,
        })
    return results


class NetworkCollector(Collector):
    """Collects network listeners and active connections."""

    name = "network"

    def collect(self) -> dict[str, Any]:
        result = {}

        # Collect TCP listeners
        for entry in _parse_net_file("/proc/net/tcp"):
            if entry["state"] == "LISTEN":
                key = f"tcp:{entry['local_addr']}"
                result[key] = {
                    "protocol": "tcp",
                    "address": entry["local_addr"],
                    "port": entry["local_port"],
                    "state": "LISTEN",
                }

        for entry in _parse_net_file("/proc/net/tcp6"):
            if entry["state"] == "LISTEN":
                key = f"tcp6:{entry['local_addr']}"
                result[key] = {
                    "protocol": "tcp6",
                    "address": entry["local_addr"],
                    "port": entry["local_port"],
                    "state": "LISTEN",
                }

        # Count established connections per port
        conn_counts: dict[int, int] = {}
        for entry in _parse_net_file("/proc/net/tcp"):
            if entry["state"] == "ESTABLISHED":
                conn_counts[entry["local_port"]] = conn_counts.get(entry["local_port"], 0) + 1

        if conn_counts:
            result["_connection_counts"] = conn_counts

        return result

    @classmethod
    def diff_entry(cls, key: str, old: Any, new: Any) -> str:
        if key == "_connection_counts":
            return f"Connection counts changed"
        if old is None:
            port = new.get("port", "?")
            return f"+ Port {port} now listening ({new.get('protocol', 'tcp')})"
        if new is None:
            port = old.get("port", "?")
            return f"- Port {port} no longer listening"
        return f"  {key}: {old} -> {new}"
