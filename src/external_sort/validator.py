"""Validation helpers for sorted CSV outputs."""

from __future__ import annotations

import csv
from pathlib import Path

from src.external_sort.keying import build_sort_key


def validate_sorted_csv(
    file_path: Path,
    sort_keys: tuple[str, ...] = ("patient_id", "date"),
) -> tuple[bool, int]:
    """Check that CSV rows are globally sorted by sort_keys."""
    rows_seen = 0
    previous_key: tuple[object, ...] | None = None

    with file_path.open("r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            current_key = build_sort_key(row, sort_keys)
            if previous_key is not None and current_key < previous_key:
                return False, rows_seen
            previous_key = current_key
            rows_seen += 1

    return True, rows_seen
