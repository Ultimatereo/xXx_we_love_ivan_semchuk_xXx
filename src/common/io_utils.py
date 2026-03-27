"""Small file-system and formatting helpers."""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> None:
    """Create directory recursively if needed."""
    path.mkdir(parents=True, exist_ok=True)


def file_size_bytes(path: Path) -> int:
    """Return file size in bytes."""
    return path.stat().st_size


def format_size(num_bytes: int) -> str:
    """Format bytes using a readable unit."""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"
